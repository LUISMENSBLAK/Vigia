from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from pyproj import Transformer
from shapely.geometry import Polygon

from services.api.vigia_api.config import Settings
from services.api.vigia_api.database import VigiaDatabase
from workers.copernicus.client import (
    CopernicusClient,
    sentinel_2_projected_request,
)

from .aoi import ResolvedAOI
from .lidar import validate_las_laz
from .models import (
    AvailabilityState,
    DownloadManifest,
    GeospatialLayer,
    GeospatialProduct,
)
from .products import (
    DerivedRaster,
    derive_lidar_cogs,
    derive_terrain_cogs,
    split_sentinel_index_cogs,
)
from .raster import validate_raster
from .repository import GeospatialRepository
from .sources import (
    CnigLidarClient,
    OfficialSourceError,
    fetch_administrative_unit,
    fetch_gisco_country,
    fetch_land_cover,
    fetch_mdt05,
    write_download,
)
from .storage import LocalStorage


class AdministrativeUnitConfig(BaseModel):
    national_code: str = Field(pattern=r"^[0-9]{11}$")
    parent: str | None = Field(default=None, pattern=r"^[0-9]{11}$")
    provider: Literal["IGN", "GISCO"] = "IGN"
    provider_id: str | None = None

    @model_validator(mode="after")
    def validate_provider_id(self) -> AdministrativeUnitConfig:
        if self.provider == "GISCO" and not self.provider_id:
            raise ValueError("GISCO requiere provider_id ISO alfa-2.")
        return self


class MaterializationConfig(BaseModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9-]+$")
    description: str
    bounds: tuple[float, float, float, float]
    crs: str
    administrative_units: list[AdministrativeUnitConfig]
    lidar_resolution_m: float = Field(gt=0, le=50)
    sentinel_resolution_m: float = Field(gt=0, le=100)
    sentinel_lookback_days: int = Field(gt=0, le=366)
    cnig_verify_tls: bool = True
    attempt_lidar_download: bool = True

    @model_validator(mode="after")
    def validate_bounds_and_parents(self) -> MaterializationConfig:
        west, south, east, north = self.bounds
        if not (west < east and south < north):
            raise ValueError("Los límites de materialización no son válidos.")
        codes = {unit.national_code for unit in self.administrative_units}
        if len(codes) != len(self.administrative_units):
            raise ValueError("Las unidades administrativas no pueden repetirse.")
        if any(
            unit.parent is not None and unit.parent not in codes
            for unit in self.administrative_units
        ):
            raise ValueError("Todo parent administrativo debe formar parte de la configuración.")
        return self


@dataclass(frozen=True, slots=True)
class MaterializationReport:
    aoi_id: str
    administrative_units: int
    terrain_products: int
    lidar_products: int
    sentinel_products: int
    land_cover_features: int
    source_products: dict[str, str]


def load_materialization_config(path: Path) -> MaterializationConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return MaterializationConfig.model_validate(payload)


def resolved_aoi(config: MaterializationConfig) -> ResolvedAOI:
    transformer = Transformer.from_crs(config.crs, "EPSG:4326", always_xy=True)
    west, south, east, north = config.bounds
    corners = [
        transformer.transform(west, south),
        transformer.transform(east, south),
        transformer.transform(east, north),
        transformer.transform(west, north),
    ]
    polygon = Polygon([*corners, corners[0]])
    return ResolvedAOI(geometry=polygon, source="configured_projected_bbox", reference=config.id)


def _hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _render_hint(layer: str) -> dict[str, Any]:
    palettes: dict[str, dict[str, Any]] = {
        "ELEVATION": {"palette": "terrain", "range": "dynamic"},
        "SLOPE": {"palette": "slope", "range": [0, 60]},
        "ASPECT": {"palette": "cyclic", "range": [0, 360]},
        "TERRAIN_RUGGEDNESS": {"palette": "terrain", "range": "dynamic"},
        "NDVI": {"palette": "vegetation", "range": [-0.2, 0.8]},
        "NDMI": {"palette": "moisture", "range": [-0.5, 0.7]},
        "NBR": {"palette": "burn-ratio", "range": [-0.5, 0.7]},
        "LIDAR_DTM": {"palette": "terrain", "range": "dynamic"},
        "LIDAR_DSM": {"palette": "terrain", "range": "dynamic"},
        "CANOPY_HEIGHT": {"palette": "vegetation", "range": [0, 40]},
        "LAND_COVER": {"palette": "categorical", "range": None},
    }
    return palettes[layer]


def _availability(derived: DerivedRaster) -> AvailabilityState:
    return (
        AvailabilityState.AVAILABLE
        if derived.quality["valid_fraction"] >= 0.99
        else AvailabilityState.PARTIAL
    )


def _manifest(
    *,
    provider: str,
    product_id: str,
    source_uri: str,
    content: bytes,
    aoi: ResolvedAOI,
    requested_at: datetime,
    downloaded_at: datetime,
) -> DownloadManifest:
    return DownloadManifest(
        provider=provider,
        product_id=product_id,
        source_uri=source_uri,
        requested_at=requested_at,
        downloaded_at=downloaded_at,
        size_bytes=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        status=AvailabilityState.AVAILABLE,
        aoi_hash=aoi.hash,
        request_id=f"phase4b-{provider.casefold().replace(' ', '-')}-{aoi.hash[:16]}",
    )


def _product(
    *,
    provider: str,
    dataset: str,
    source_product_id: str,
    derived: DerivedRaster,
    aoi: ResolvedAOI,
    source_uri: str,
    storage_uri: str,
    input_hashes: tuple[str, ...],
    output_hash: str,
    source_resolution_m: float | None,
    observed_at: datetime | None,
    processed_at: datetime,
    software_version: str,
) -> GeospatialProduct:
    configuration = {
        "aoi_hash": aoi.hash,
        "layer": derived.layer,
        "algorithm": derived.algorithm,
        "output_resolution_m": derived.validation.resolution[0],
    }
    return GeospatialProduct(
        provider=provider,
        dataset=dataset,
        product_id=f"{source_product_id}:{derived.layer}",
        layer=GeospatialLayer(derived.layer),
        availability=_availability(derived),
        observed_at=observed_at,
        processed_at=processed_at,
        source_uri=source_uri,
        storage_uri=storage_uri,
        footprint_geojson=aoi.geojson,
        source_crs=derived.validation.crs,
        output_crs=derived.validation.crs,
        source_resolution_m=source_resolution_m,
        output_resolution_m=derived.validation.resolution[0],
        resampling_algorithm="nearest" if derived.layer == "ASPECT" else "average",
        nodata=derived.validation.nodata,
        raster_band=1,
        value_units=derived.units,
        published_at=processed_at,
        quality=derived.quality,
        input_hashes=input_hashes,
        output_hash=output_hash,
        configuration_hash=_hash(configuration),
        software_version=software_version,
        algorithm=derived.algorithm,
        render_hint=_render_hint(derived.layer),
    )


async def _persist_derived(
    *,
    repository: GeospatialRepository,
    storage: LocalStorage,
    source_code: str,
    provider: str,
    dataset: str,
    dataset_version: str,
    source_product_id: str,
    source_uri: str,
    source_resolution_m: float | None,
    observed_at: datetime | None,
    processed_at: datetime,
    raw_hashes: tuple[str, ...],
    derived_items: list[DerivedRaster],
    aoi: ResolvedAOI,
    software_version: str,
    code_commit: str,
    manifest: DownloadManifest | None,
) -> int:
    for index, derived in enumerate(derived_items):
        key = (
            f"processed/{provider.casefold().replace(' ', '-')}/"
            f"{aoi.hash[:16]}/{derived.layer.casefold()}.cog.tif"
        )
        storage_uri, output_hash = storage.put(key, derived.content)
        product = _product(
            provider=provider,
            dataset=dataset,
            source_product_id=source_product_id,
            derived=derived,
            aoi=aoi,
            source_uri=source_uri,
            storage_uri=storage_uri,
            input_hashes=raw_hashes,
            output_hash=output_hash,
            source_resolution_m=source_resolution_m,
            observed_at=observed_at,
            processed_at=processed_at,
            software_version=software_version,
        )
        await repository.persist_product(
            source_code=source_code,
            product=product,
            manifest=manifest if index == 0 else None,
            dataset_version=dataset_version,
            code_commit=code_commit,
            raster_metadata=asdict(derived.validation),
        )
    return len(derived_items)


async def materialize(
    *,
    config: MaterializationConfig,
    settings: Settings,
    storage_root: Path,
    code_commit: str,
) -> MaterializationReport:
    if settings.SUPABASE_DB_URL is None:
        raise ValueError("SUPABASE_DB_URL es obligatorio para materializar el catálogo.")
    database = VigiaDatabase(settings.SUPABASE_DB_URL.get_secret_value())
    repository = GeospatialRepository(database)
    storage = LocalStorage(storage_root)
    aoi = resolved_aoi(config)
    now = datetime.now(UTC)
    software_version = "vigia/0.4.0"
    source_products: dict[str, str] = {}
    try:
        units = await asyncio.gather(
            *(
                fetch_gisco_country(
                    unit.provider_id or "", national_code=unit.national_code
                )
                if unit.provider == "GISCO"
                else fetch_administrative_unit(unit.national_code)
                for unit in config.administrative_units
            )
        )
        administrative_count = await repository.persist_administrative_units(
            list(units),
            dataset_version=now.date().isoformat(),
            parent_by_code={
                unit.national_code: unit.parent for unit in config.administrative_units
            },
        )

        requested_at = datetime.now(UTC)
        mdt_content, mdt_uri = await fetch_mdt05(bounds_etrs89_utm30=config.bounds)
        downloaded_at = datetime.now(UTC)
        raw_mdt_uri, raw_mdt_hash = storage.put(
            f"raw/ign-mdt05/{aoi.hash[:16]}.tif", mdt_content
        )
        with TemporaryDirectory(prefix="vigia-mdt05-") as directory:
            mdt_path = Path(directory) / "mdt05.tif"
            write_download(mdt_path, mdt_content)
            validate_raster(mdt_path)
            terrain = derive_terrain_cogs(mdt_path)
        terrain_count = await _persist_derived(
            repository=repository,
            storage=storage,
            source_code="IGN_MDT05",
            provider="IGN",
            dataset="MDT05",
            dataset_version="MDT05",
            source_product_id=f"IGN-MDT05-{config.id}",
            source_uri=mdt_uri,
            source_resolution_m=5.0,
            observed_at=None,
            processed_at=downloaded_at,
            raw_hashes=(raw_mdt_hash,),
            derived_items=terrain,
            aoi=aoi,
            software_version=software_version,
            code_commit=code_commit,
            manifest=_manifest(
                provider="IGN",
                product_id=f"IGN-MDT05-{config.id}",
                source_uri=mdt_uri,
                content=mdt_content,
                aoi=aoi,
                requested_at=requested_at,
                downloaded_at=downloaded_at,
            ),
        )
        source_products["terrain_raw"] = raw_mdt_uri

        lidar_count = 0
        lidar_item = None
        requested_at = datetime.now(UTC)
        try:
            centroid = aoi.geometry.centroid
            lidar_client = CnigLidarClient(verify_tls=config.cnig_verify_tls)
            lidar_item = await lidar_client.locate(
                longitude=centroid.x, latitude=centroid.y
            )
            requested_at = datetime.now(UTC)
            if not config.attempt_lidar_download:
                raise OfficialSourceError(
                    "Reintento LiDAR omitido tras una descarga incompleta ya verificada."
                )
            lidar_key = f"raw/pnoa-cnig/{lidar_item.filename}"
            lidar_content = (
                storage.get(lidar_key)
                if storage.exists(lidar_key)
                else await lidar_client.download(lidar_item)
            )
            downloaded_at = datetime.now(UTC)
            # Validate and derive before admitting the raw object to the cache. A
            # truncated LAZ must never become a reusable or AVAILABLE input.
            with TemporaryDirectory(prefix="vigia-lidar-") as directory:
                lidar_path = Path(directory) / lidar_item.filename
                write_download(lidar_path, lidar_content)
                validation = validate_las_laz(lidar_path)
                lidar = derive_lidar_cogs(
                    lidar_path, resolution_m=config.lidar_resolution_m
                )
            raw_lidar_uri, raw_lidar_hash = storage.put(lidar_key, lidar_content)
            lidar_count = await _persist_derived(
                repository=repository,
                storage=storage,
                source_code="PNOA_CNIG",
                provider="PNOA-CNIG",
                dataset="LiDAR-PNOA-cob3",
                dataset_version=str(lidar_item.observed_year or "NO_VERIFICADO"),
                source_product_id=lidar_item.filename,
                source_uri=lidar_item.source_uri,
                source_resolution_m=None,
                observed_at=None,
                processed_at=downloaded_at,
                raw_hashes=(raw_lidar_hash,),
                derived_items=lidar,
                aoi=aoi,
                software_version=software_version,
                code_commit=code_commit,
                manifest=_manifest(
                    provider="PNOA-CNIG",
                    product_id=lidar_item.filename,
                    source_uri=lidar_item.source_uri,
                    content=lidar_content,
                    aoi=aoi,
                    requested_at=requested_at,
                    downloaded_at=downloaded_at,
                ),
            )
            await repository.record_source_health(
                source_code="PNOA_CNIG",
                service_state="OPERATIVO",
                detail="Catálogo, descarga y tesela LiDAR PNOA validados y materializados.",
                checked_at=downloaded_at,
                last_product_at=None,
                last_ingest_at=downloaded_at,
                check_interval_seconds=86400,
                product_freshness_seconds=31536000,
            )
            source_products["lidar_raw"] = raw_lidar_uri
            source_products["lidar_point_count"] = str(validation.point_count)
        except (OfficialSourceError, ValueError):
            if lidar_item is not None:
                await repository.persist_download_manifest(
                    source_code="PNOA_CNIG",
                    manifest=DownloadManifest(
                        provider="PNOA-CNIG",
                        product_id=lidar_item.filename,
                        source_uri=lidar_item.source_uri,
                        requested_at=requested_at,
                        status=AvailabilityState.ERROR,
                        aoi_hash=aoi.hash,
                        error_code="PNOA_DOWNLOAD_INCOMPLETE",
                        request_id=f"phase4b-pnoa-cnig-{aoi.hash[:16]}",
                    ),
                )
            await repository.record_source_health(
                source_code="PNOA_CNIG",
                service_state="DEGRADADO",
                detail=(
                    "Catálogo PNOA disponible; la descarga oficial no produjo una "
                    "tesela LAZ completa y validable. Ningún derivado fue publicado."
                ),
                error_code="PNOA_DOWNLOAD_INCOMPLETE",
                check_interval_seconds=86400,
                product_freshness_seconds=31536000,
            )
            source_products["lidar_status"] = "BLOCKED"

        if settings.COPERNICUS_CLIENT_ID is None or settings.COPERNICUS_CLIENT_SECRET is None:
            raise ValueError("Credenciales Copernicus no disponibles.")
        copernicus = CopernicusClient(
            settings.COPERNICUS_CLIENT_ID.get_secret_value(),
            settings.COPERNICUS_CLIENT_SECRET.get_secret_value(),
            token_url=settings.COPERNICUS_TOKEN_URL,
            base_url=settings.COPERNICUS_SH_BASE_URL,
        )
        west, south, east, north = aoi.geometry.bounds
        catalogue = await copernicus.catalog_search(
            collection="sentinel-2-l2a",
            bbox=(west, south, east, north),
            start=now - timedelta(days=config.sentinel_lookback_days),
            end=now,
            limit=100,
        )
        candidates = [
            feature
            for feature in catalogue.get("features", [])
            if isinstance(feature, dict)
            and isinstance(feature.get("properties"), dict)
            and feature["properties"].get("datetime")
            and float(feature["properties"].get("eo:cloud_cover", 101)) <= 30
        ]
        if not candidates:
            raise ValueError("Copernicus no devolvió un Sentinel-2 L2A utilizable.")
        selected = max(
            candidates,
            key=lambda feature: str(feature["properties"]["datetime"]),
        )
        selected_at = datetime.fromisoformat(
            str(selected["properties"]["datetime"]).replace("Z", "+00:00")
        )
        day_start = selected_at.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1) - timedelta(microseconds=1)
        pixel_width = round((config.bounds[2] - config.bounds[0]) / config.sentinel_resolution_m)
        pixel_height = round((config.bounds[3] - config.bounds[1]) / config.sentinel_resolution_m)
        utm_bounds = config.bounds
        if config.crs != "EPSG:32630":
            transformer = Transformer.from_crs(config.crs, "EPSG:32630", always_xy=True)
            projected_west, projected_south = transformer.transform(
                config.bounds[0], config.bounds[1]
            )
            projected_east, projected_north = transformer.transform(
                config.bounds[2], config.bounds[3]
            )
            utm_bounds = (
                projected_west,
                projected_south,
                projected_east,
                projected_north,
            )
        requested_at = datetime.now(UTC)
        source_stack = await copernicus.process(
            sentinel_2_projected_request(
                bounds=utm_bounds,
                crs_epsg=32630,
                start=day_start,
                end=day_end,
                width=pixel_width,
                height=pixel_height,
                source_bands=True,
            )
        )
        index_stack = await copernicus.process(
            sentinel_2_projected_request(
                bounds=utm_bounds,
                crs_epsg=32630,
                start=day_start,
                end=day_end,
                width=pixel_width,
                height=pixel_height,
            )
        )
        downloaded_at = datetime.now(UTC)
        sentinel_id = str(selected["id"])
        raw_source_uri, source_hash = storage.put(
            f"raw/copernicus-sentinel-2/{hashlib.sha256(sentinel_id.encode()).hexdigest()[:24]}"
            "-bands.tif",
            source_stack,
        )
        raw_index_uri, index_hash = storage.put(
            f"raw/copernicus-sentinel-2/{hashlib.sha256(sentinel_id.encode()).hexdigest()[:24]}"
            "-indices.tif",
            index_stack,
        )
        with TemporaryDirectory(prefix="vigia-sentinel-") as directory:
            sentinel_path = Path(directory) / "indices.tif"
            write_download(sentinel_path, index_stack)
            sentinel = split_sentinel_index_cogs(sentinel_path)
        sentinel = [
            DerivedRaster(
                layer=item.layer,
                content=item.content,
                validation=item.validation,
                units=item.units,
                algorithm=item.algorithm,
                quality={
                    **item.quality,
                    "source_product_id": sentinel_id,
                    "source_bands": ["B04", "B08", "B11", "B12", "SCL", "dataMask"],
                    "source_band_storage_uri": raw_source_uri,
                    "scene_cloud_cover_pct": selected["properties"].get("eo:cloud_cover"),
                    "processing_level": "L2A",
                },
            )
            for item in sentinel
        ]
        sentinel_count = await _persist_derived(
            repository=repository,
            storage=storage,
            source_code="COPERNICUS_SENTINEL_2",
            provider="Copernicus",
            dataset="Sentinel-2 L2A",
            dataset_version="N0512",
            source_product_id=sentinel_id,
            source_uri=f"{settings.COPERNICUS_SH_BASE_URL}/catalog/v1/search",
            source_resolution_m=config.sentinel_resolution_m,
            observed_at=selected_at,
            processed_at=downloaded_at,
            raw_hashes=(source_hash, index_hash),
            derived_items=sentinel,
            aoi=aoi,
            software_version=software_version,
            code_commit=code_commit,
            manifest=_manifest(
                provider="Copernicus",
                product_id=sentinel_id,
                source_uri=f"{settings.COPERNICUS_SH_BASE_URL}/catalog/v1/search",
                content=index_stack,
                aoi=aoi,
                requested_at=requested_at,
                downloaded_at=downloaded_at,
            ),
        )
        await repository.record_source_health(
            source_code="COPERNICUS_SENTINEL_2",
            service_state="OPERATIVO",
            detail="OAuth, catálogo y Process API verificados; producto L2A materializado.",
            checked_at=downloaded_at,
            last_product_at=selected_at,
            last_ingest_at=downloaded_at,
            check_interval_seconds=604800,
            product_freshness_seconds=1209600,
        )
        source_products["sentinel_source_bands"] = raw_source_uri
        source_products["sentinel_index_stack"] = raw_index_uri
        source_products["sentinel_product_id"] = sentinel_id

        requested_at = datetime.now(UTC)
        land_features, pages, land_uri = await fetch_land_cover(aoi)
        downloaded_at = datetime.now(UTC)
        if not land_features:
            raise ValueError("SIOSE AR no devolvió unidades para la AOI.")
        land_geojson = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": feature.external_id,
                        "geometry": feature.geometry_geojson,
                        "properties": {
                            "class_uri": feature.class_uri,
                            "class_code": feature.class_code,
                            "covered_percentage": feature.covered_percentage,
                            "observed_at": (
                                feature.observed_at.isoformat()
                                if feature.observed_at is not None
                                else None
                            ),
                        },
                    }
                    for feature in land_features
                ],
            },
            separators=(",", ":"),
        ).encode()
        land_storage_uri, land_hash = storage.put(
            f"processed/ign-siose-ar-2017/{aoi.hash[:16]}.geojson", land_geojson
        )
        land_processed_at = downloaded_at
        land_observed_values = [
            feature.observed_at for feature in land_features if feature.observed_at is not None
        ]
        land_observed_at = max(land_observed_values) if land_observed_values else None
        page_hashes = tuple(hashlib.sha256(page).hexdigest() for page in pages)
        land_product = GeospatialProduct(
            provider="IGN / IDEE",
            dataset="SIOSE AR 2017",
            product_id=f"SIOSE-AR-2017:{config.id}:LAND_COVER",
            layer=GeospatialLayer.LAND_COVER,
            availability=AvailabilityState.AVAILABLE,
            observed_at=land_observed_at,
            processed_at=land_processed_at,
            source_uri=land_uri,
            storage_uri=land_storage_uri,
            footprint_geojson=aoi.geojson,
            source_crs="EPSG:4326",
            output_crs="EPSG:4326",
            source_resolution_m=None,
            output_resolution_m=None,
            resampling_algorithm=None,
            nodata=None,
            raster_band=None,
            value_units="CODIIGEValue",
            published_at=land_processed_at,
            quality={
                "feature_count": len(land_features),
                "dataset": "siose_ar2017",
                "nomenclature": "CODIIGEValue",
                "not_a_fuel_model": True,
            },
            input_hashes=page_hashes,
            output_hash=land_hash,
            configuration_hash=_hash(
                {"aoi_hash": aoi.hash, "dataset": "siose_ar2017", "clip": True}
            ),
            software_version=software_version,
            algorithm="wfs_pagination_gml32_clip_v1",
            render_hint=_render_hint("LAND_COVER"),
        )
        land_product_id = await repository.persist_product(
            source_code="IGN_SIOSE_AR_2017",
            product=land_product,
            manifest=_manifest(
                provider="IGN-IDEE",
                product_id=f"SIOSE-AR-2017:{config.id}",
                source_uri=land_uri,
                content=land_geojson,
                aoi=aoi,
                requested_at=requested_at,
                downloaded_at=downloaded_at,
            ),
            dataset_version="siose_ar2017",
            code_commit=code_commit,
            raster_metadata={"format": "GeoJSON", "feature_count": len(land_features)},
        )
        land_cover_count = await repository.persist_land_cover_features(
            land_product_id, land_features
        )
        source_products["land_cover"] = land_storage_uri
        return MaterializationReport(
            aoi_id=config.id,
            administrative_units=administrative_count,
            terrain_products=terrain_count,
            lidar_products=lidar_count,
            sentinel_products=sentinel_count,
            land_cover_features=land_cover_count,
            source_products=source_products,
        )
    finally:
        await database.close()
