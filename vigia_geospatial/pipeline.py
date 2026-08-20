import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pyproj import CRS

from .aoi import ResolvedAOI
from .models import (
    AvailabilityState,
    DownloadManifest,
    GeospatialLayer,
    GeospatialProduct,
)
from .raster import create_cog, validate_metric_raster_crs, validate_raster
from .storage import ObjectStorage

logger = logging.getLogger("vigia.geospatial")


@dataclass(frozen=True, slots=True)
class RasterCatalogItem:
    provider: str
    dataset: str
    product_id: str
    source_uri: str
    observed_at: datetime | None
    footprint_geojson: dict[str, Any]
    source_resolution_m: float
    source_crs: str
    quality: dict[str, Any]
    etag: str | None = None


@dataclass(frozen=True, slots=True)
class RasterIngestResult:
    manifest: DownloadManifest
    product: GeospatialProduct


def ingest_raster_bytes(
    *,
    item: RasterCatalogItem,
    layer: GeospatialLayer,
    aoi: ResolvedAOI,
    content: bytes,
    storage: ObjectStorage,
    configuration_hash: str,
    software_version: str,
    algorithm: str,
    request_id: str,
    output_crs: str | None = None,
    output_resolution_m: float | None = None,
    resampling_algorithm: str = "average",
    processed_at: datetime | None = None,
    is_experimental: bool = False,
) -> RasterIngestResult:
    """Validate a bounded raster, convert it to COG and create provenance-ready metadata."""
    requested_at = datetime.now(UTC)
    if not content:
        raise ValueError("La descarga raster está vacía.")
    input_hash = hashlib.sha256(content).hexdigest()
    safe_product = hashlib.sha256(item.product_id.encode()).hexdigest()[:24]
    raw_key = f"raw/{item.provider.casefold().replace(' ', '-')}/{safe_product}.tif"
    cog_key = f"cog/{layer.value.casefold()}/{safe_product}-{configuration_hash[:12]}.tif"

    with TemporaryDirectory(prefix="vigia-geospatial-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        raw_path = temporary_root / "input.tif"
        cog_path = temporary_root / "output.cog.tif"
        raw_path.write_bytes(content)
        raw_validation = validate_raster(raw_path)
        validate_metric_raster_crs(raw_path)
        if CRS.from_user_input(raw_validation.crs) != CRS.from_user_input(item.source_crs):
            raise ValueError("El CRS raster no coincide con el catálogo oficial.")
        cog_validation = create_cog(
            raw_path, cog_path, resampling=resampling_algorithm
        )
        actual_output_crs = CRS.from_user_input(cog_validation.crs)
        if output_crs is not None and actual_output_crs != CRS.from_user_input(output_crs):
            raise ValueError(
                "La conversión COG no reproyecta; el CRS de salida solicitado difiere."
            )
        raw_uri, stored_input_hash = storage.put(raw_key, content)
        if stored_input_hash != input_hash:
            raise ValueError("El hash del objeto raw no coincide con la descarga.")
        cog_content = cog_path.read_bytes()
        storage_uri, output_hash = storage.put(cog_key, cog_content)

    completed_at = processed_at or datetime.now(UTC)
    manifest = DownloadManifest(
        provider=item.provider,
        product_id=item.product_id,
        source_uri=item.source_uri,
        requested_at=requested_at,
        downloaded_at=completed_at,
        size_bytes=len(content),
        checksum_sha256=input_hash,
        etag=item.etag,
        status=AvailabilityState.AVAILABLE,
        aoi_hash=aoi.hash,
        request_id=request_id,
    )
    product = GeospatialProduct(
        provider=item.provider,
        dataset=item.dataset,
        product_id=item.product_id,
        layer=layer,
        availability=AvailabilityState.AVAILABLE,
        observed_at=item.observed_at,
        processed_at=completed_at,
        source_uri=item.source_uri,
        storage_uri=storage_uri,
        footprint_geojson=item.footprint_geojson,
        source_crs=raw_validation.crs,
        output_crs=cog_validation.crs,
        source_resolution_m=item.source_resolution_m,
        output_resolution_m=output_resolution_m or cog_validation.resolution[0],
        resampling_algorithm=resampling_algorithm,
        nodata=cog_validation.nodata,
        quality={
            **item.quality,
            "cog": cog_validation.is_cog,
            "tiled": cog_validation.tiled,
            "overviews": cog_validation.overviews,
            "raw_storage_uri": raw_uri,
        },
        input_hashes=(input_hash,),
        output_hash=output_hash,
        configuration_hash=configuration_hash,
        software_version=software_version,
        algorithm=algorithm,
        is_experimental=is_experimental,
    )
    logger.info(
        "geospatial_ingest_completed",
        extra={
            "product_id": item.product_id,
            "aoi": aoi.hash,
            "layer": layer.value,
            "download_run": input_hash[:16],
            "processing_run": configuration_hash[:16],
        },
    )
    return RasterIngestResult(manifest=manifest, product=product)
