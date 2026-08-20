from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from services.api.vigia_api.database import VigiaDatabase

from .models import DownloadManifest, GeospatialProduct
from .sources import AdministrativeUnit, LandCoverFeature


class GeospatialPersistenceError(RuntimeError):
    pass


class GeospatialRepository:
    def __init__(self, database: VigiaDatabase) -> None:
        self._database = database

    async def persist_administrative_units(
        self,
        units: list[AdministrativeUnit],
        *,
        dataset_version: str,
        parent_by_code: dict[str, str | None],
    ) -> int:
        written = 0
        async with self._database.transaction() as connection:
            ids: dict[str, UUID] = {}
            ordered = sorted(
                units,
                key=lambda item: {
                    "COUNTRY": 0,
                    "AUTONOMOUS_COMMUNITY": 1,
                    "PROVINCE": 2,
                    "MUNICIPALITY": 3,
                }[item.level],
            )
            for unit in ordered:
                source_id = await connection.scalar(
                    text("select id from vigia.sources where code = :source_code"),
                    {"source_code": unit.source_code},
                )
                if source_id is None:
                    raise GeospatialPersistenceError(
                        f"Falta la fuente administrativa {unit.source_code}."
                    )
                parent_code = parent_by_code.get(unit.national_code)
                parent_id = ids.get(parent_code) if parent_code else None
                row = (
                    await connection.execute(
                        text(
                            """
                            insert into vigia.administrative_areas (
                              source_id, external_id, name, level, parent_id,
                              geometry, dataset_version
                            ) values (
                              :source_id, :external_id, :name,
                              cast(:level as vigia.administrative_level), :parent_id,
                              extensions.st_multi(
                                extensions.st_setsrid(
                                  extensions.st_geomfromgeojson(:geometry), 4326
                                )
                              ),
                              :dataset_version
                            )
                            on conflict (source_id, external_id, dataset_version) do update set
                              name = excluded.name,
                              level = excluded.level,
                              parent_id = excluded.parent_id,
                              geometry = excluded.geometry
                            returning id
                            """
                        ),
                        {
                            "source_id": source_id,
                            "external_id": unit.external_id,
                            "name": unit.name,
                            "level": unit.level,
                            "parent_id": parent_id,
                            "geometry": json.dumps(unit.geometry_geojson, separators=(",", ":")),
                            "dataset_version": dataset_version,
                        },
                    )
                ).mappings().one()
                ids[unit.national_code] = row["id"]
                written += 1
        return written

    async def persist_product(
        self,
        *,
        source_code: str,
        product: GeospatialProduct,
        manifest: DownloadManifest | None,
        dataset_version: str,
        code_commit: str,
        raster_metadata: dict[str, Any],
    ) -> UUID:
        if product.output_hash is None or product.processed_at is None:
            raise GeospatialPersistenceError("El producto requiere hash y fecha de procesamiento.")
        async with self._database.transaction() as connection:
            source_id = await connection.scalar(
                text("select id from vigia.sources where code = :code"),
                {"code": source_code},
            )
            if source_id is None:
                raise GeospatialPersistenceError(f"Falta la fuente de catálogo {source_code}.")
            row = (
                await connection.execute(
                    text(
                        """
                        insert into vigia.geospatial_products (
                          source_id, product_id, layer, availability, observed_at, processed_at,
                          footprint, source_uri, storage_uri, source_crs, output_crs,
                          source_resolution_m, output_resolution_m, resampling_algorithm,
                          nodata, raster_metadata, quality, input_hashes, output_hash,
                          configuration_hash, software_version, algorithm, is_experimental,
                          raster_band, value_units, published_at, render_hint
                        ) values (
                          :source_id, :product_id, :layer,
                          cast(:availability as vigia.geospatial_availability),
                          :observed_at, :processed_at,
                          extensions.st_multi(
                            extensions.st_setsrid(
                              extensions.st_geomfromgeojson(:footprint), 4326
                            )
                          ),
                          :source_uri, :storage_uri, :source_crs, :output_crs,
                          :source_resolution_m, :output_resolution_m, :resampling_algorithm,
                          :nodata, cast(:raster_metadata as jsonb), cast(:quality as jsonb),
                          :input_hashes, :output_hash, :configuration_hash, :software_version,
                          :algorithm, :is_experimental, :raster_band, :value_units,
                          :published_at, cast(:render_hint as jsonb)
                        )
                        on conflict (source_id, product_id, layer, configuration_hash) do update set
                          availability = excluded.availability,
                          observed_at = excluded.observed_at,
                          processed_at = excluded.processed_at,
                          footprint = excluded.footprint,
                          source_uri = excluded.source_uri,
                          storage_uri = excluded.storage_uri,
                          raster_metadata = excluded.raster_metadata,
                          quality = excluded.quality,
                          input_hashes = excluded.input_hashes,
                          output_hash = excluded.output_hash,
                          published_at = excluded.published_at,
                          invalidated_at = null,
                          render_hint = excluded.render_hint
                        returning id
                        """
                    ),
                    {
                        "source_id": source_id,
                        "product_id": product.product_id,
                        "layer": product.layer.value,
                        "availability": product.availability.value,
                        "observed_at": product.observed_at,
                        "processed_at": product.processed_at,
                        "footprint": json.dumps(product.footprint_geojson, separators=(",", ":")),
                        "source_uri": product.source_uri,
                        "storage_uri": product.storage_uri,
                        "source_crs": product.source_crs,
                        "output_crs": product.output_crs,
                        "source_resolution_m": product.source_resolution_m,
                        "output_resolution_m": product.output_resolution_m,
                        "resampling_algorithm": product.resampling_algorithm,
                        "nodata": product.nodata,
                        "raster_metadata": json.dumps(raster_metadata, separators=(",", ":")),
                        "quality": json.dumps(product.quality, separators=(",", ":")),
                        "input_hashes": list(product.input_hashes),
                        "output_hash": product.output_hash,
                        "configuration_hash": product.configuration_hash,
                        "software_version": product.software_version,
                        "algorithm": product.algorithm,
                        "is_experimental": product.is_experimental,
                        "raster_band": product.raster_band,
                        "value_units": product.value_units,
                        "published_at": product.published_at or product.processed_at,
                        "render_hint": json.dumps(product.render_hint, separators=(",", ":")),
                    },
                )
            ).mappings().one()
            product_row_id: UUID = row["id"]
            await connection.execute(
                text(
                    """
                    update vigia.geospatial_products
                    set invalidated_at = :invalidated_at, superseded_by = :superseded_by
                    where source_id = :source_id
                      and product_id = :logical_product_id
                      and layer = :layer
                      and id <> :superseded_by
                      and invalidated_at is null
                    """
                ),
                {
                    "invalidated_at": product.processed_at,
                    "superseded_by": product_row_id,
                    "source_id": source_id,
                    "logical_product_id": product.product_id,
                    "layer": product.layer.value,
                },
            )
            provenance_id = await connection.scalar(
                text(
                    """
                    insert into vigia.data_provenance (
                      entity_type, entity_id, dataset, dataset_version, source_timestamp,
                      transformation, code_commit, parameters, input_hashes, output_hash
                    ) values (
                      'geospatial_product', :entity_id, :dataset, :dataset_version,
                      :source_timestamp, :transformation, :code_commit,
                      cast(:parameters as jsonb), :input_hashes, :output_hash
                    ) returning id
                    """
                ),
                {
                    "entity_id": product_row_id,
                    "dataset": product.dataset,
                    "dataset_version": dataset_version,
                    "source_timestamp": product.observed_at or product.processed_at,
                    "transformation": product.algorithm,
                    "code_commit": code_commit,
                    "parameters": json.dumps(
                        {
                            "configuration_hash": product.configuration_hash,
                            "source_crs": product.source_crs,
                            "output_crs": product.output_crs,
                            "source_resolution_m": product.source_resolution_m,
                            "output_resolution_m": product.output_resolution_m,
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    "input_hashes": list(product.input_hashes),
                    "output_hash": product.output_hash,
                },
            )
            await connection.execute(
                text(
                    "update vigia.geospatial_products set provenance_id = :provenance_id "
                    "where id = :product_id"
                ),
                {"provenance_id": provenance_id, "product_id": product_row_id},
            )
            if manifest is not None:
                await connection.execute(
                    text(
                        """
                        insert into vigia.download_manifests (
                          source_id, product_id, source_uri, requested_at, downloaded_at,
                          size_bytes, checksum_sha256, etag, status, aoi_hash,
                          error_code, request_id
                        ) values (
                          :source_id, :product_id, :source_uri, :requested_at, :downloaded_at,
                          :size_bytes, :checksum_sha256, :etag,
                          cast(:status as vigia.geospatial_availability), :aoi_hash,
                          :error_code, :request_id
                        )
                        on conflict (source_id, product_id, aoi_hash) do update set
                          downloaded_at = excluded.downloaded_at,
                          size_bytes = excluded.size_bytes,
                          checksum_sha256 = excluded.checksum_sha256,
                          etag = excluded.etag,
                          status = excluded.status,
                          error_code = excluded.error_code,
                          request_id = excluded.request_id
                        """
                    ),
                    {
                        "source_id": source_id,
                        **manifest.model_dump(mode="python"),
                        "status": manifest.status.value,
                    },
                )
        return product_row_id

    async def persist_land_cover_features(
        self, product_id: UUID, features: list[LandCoverFeature]
    ) -> int:
        payload = [
            {
                "product_id": product_id,
                "external_id": feature.external_id,
                "class_uri": feature.class_uri,
                "class_code": feature.class_code,
                "covered_percentage": feature.covered_percentage,
                "observed_at": feature.observed_at,
                "geometry": json.dumps(feature.geometry_geojson, separators=(",", ":")),
                "properties": json.dumps(feature.properties, separators=(",", ":")),
            }
            for feature in features
        ]
        if not payload:
            return 0
        async with self._database.transaction() as connection:
            await connection.execute(
                text(
                    """
                    insert into vigia.land_cover_features (
                      product_id, external_id, class_uri, class_code, covered_percentage,
                      observed_at, geometry, properties
                    ) values (
                      :product_id, :external_id, :class_uri, :class_code, :covered_percentage,
                      :observed_at,
                      extensions.st_multi(
                        extensions.st_setsrid(
                          extensions.st_geomfromgeojson(:geometry), 4326
                        )
                      ),
                      cast(:properties as jsonb)
                    )
                    on conflict (product_id, external_id) do update set
                      class_uri = excluded.class_uri,
                      class_code = excluded.class_code,
                      covered_percentage = excluded.covered_percentage,
                      observed_at = excluded.observed_at,
                      geometry = excluded.geometry,
                      properties = excluded.properties
                    """
                ),
                payload,
            )
        return len(payload)

    async def record_source_health(
        self,
        *,
        source_code: str,
        service_state: str,
        detail: str,
        checked_at: datetime | None = None,
        last_product_at: datetime | None = None,
        last_ingest_at: datetime | None = None,
        error_code: str | None = None,
        check_interval_seconds: int,
        product_freshness_seconds: int,
    ) -> None:
        checked = checked_at or datetime.now(UTC)
        async with self._database.transaction() as connection:
            await connection.execute(
                text(
                    """
                    insert into vigia.source_health (
                      source_id, state, checked_at, last_success_at, last_product_at,
                      last_ingest_at, last_observed_at, last_received_at,
                      check_interval_seconds, product_freshness_seconds, error_code, detail
                    )
                    select id, cast(:service_state as vigia.source_state),
                      cast(:checked_at as timestamptz),
                      case when cast(:service_state as vigia.source_state) = 'OPERATIVO'
                        then cast(:checked_at as timestamptz) else null end,
                      cast(:last_product_at as timestamptz),
                      cast(:last_ingest_at as timestamptz),
                      cast(:last_product_at as timestamptz),
                      cast(:last_ingest_at as timestamptz),
                      :check_interval_seconds, :product_freshness_seconds, :error_code, :detail
                    from vigia.sources where code = :source_code
                    on conflict (source_id) do update set
                      state = excluded.state,
                      checked_at = excluded.checked_at,
                      last_success_at = case
                        when excluded.state = 'OPERATIVO' then excluded.checked_at
                        else vigia.source_health.last_success_at
                      end,
                      last_product_at = coalesce(
                        excluded.last_product_at, vigia.source_health.last_product_at
                      ),
                      last_ingest_at = coalesce(
                        excluded.last_ingest_at, vigia.source_health.last_ingest_at
                      ),
                      last_observed_at = coalesce(
                        excluded.last_observed_at, vigia.source_health.last_observed_at
                      ),
                      last_received_at = coalesce(
                        excluded.last_received_at, vigia.source_health.last_received_at
                      ),
                      check_interval_seconds = excluded.check_interval_seconds,
                      product_freshness_seconds = excluded.product_freshness_seconds,
                      error_code = excluded.error_code,
                      detail = excluded.detail
                    """
                ),
                {
                    "source_code": source_code,
                    "service_state": service_state,
                    "checked_at": checked,
                    "last_product_at": last_product_at,
                    "last_ingest_at": last_ingest_at,
                    "check_interval_seconds": check_interval_seconds,
                    "product_freshness_seconds": product_freshness_seconds,
                    "error_code": error_code,
                    "detail": detail,
                },
            )
