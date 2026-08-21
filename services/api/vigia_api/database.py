from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


class DatabaseUnavailableError(RuntimeError):
    """A sanitized database error that is safe to expose in source health."""


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    checked_at: datetime
    postgis_version: str


def _async_url(raw_url: str) -> URL:
    url = make_url(raw_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+asyncpg")
    if url.drivername != "postgresql+asyncpg":
        raise ValueError("SUPABASE_DB_URL debe ser una URL PostgreSQL.")
    return url


class VigiaDatabase:
    def __init__(self, raw_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            _async_url(raw_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_recycle=300,
        )

    async def close(self) -> None:
        await self._engine.dispose()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection]:
        async with self._engine.begin() as connection:
            yield connection

    async def health(self) -> DatabaseHealth:
        try:
            async with self._engine.connect() as connection:
                postgis_version = await connection.scalar(
                    text("select extensions.postgis_version()")
                )
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudo verificar Supabase/PostGIS.") from exc
        if not isinstance(postgis_version, str):
            raise DatabaseUnavailableError("PostGIS no devolvió una versión verificable.")
        return DatabaseHealth(checked_at=datetime.now(UTC), postgis_version=postgis_version)

    async def source_health(self) -> list[dict[str, Any]]:
        statement = text(
            """
            select code, name, service_state::text, checked_at, last_success_at,
                   last_product_at, last_ingest_at, last_observed_at, last_received_at,
                   latency_seconds, data_freshness, service_check_overdue,
                   error_code, detail
            from api.source_health
            order by name
            """
        )
        try:
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudo consultar el estado de fuentes.") from exc
        return [dict(row) for row in rows]

    async def fire_observations(self, *, limit: int = 5000) -> list[dict[str, Any]]:
        statement = text(
            """
            select
              o.id::text,
              s.name as source,
              o.platform,
              o.sensor,
              o.observed_at,
              o.received_at,
              o.confidence_raw,
              o.brightness_kelvin,
              o.frp_mw,
              o.daynight,
              extensions.st_x(o.location::extensions.geometry) as longitude,
              extensions.st_y(o.location::extensions.geometry) as latitude,
              greatest(0, extract(epoch from (now() - o.observed_at)))::bigint as age_seconds,
              case when p.id is null then null else jsonb_build_object(
                'dataset', p.dataset,
                'dataset_version', p.dataset_version,
                'source_timestamp', p.source_timestamp,
                'transformation', p.transformation,
                'code_commit', p.code_commit,
                'input_hashes', p.input_hashes,
                'output_hash', p.output_hash
              ) end as provenance
            from vigia.fire_observations o
            join vigia.sources s on s.id = o.source_id
            left join lateral (
              select dp.*
              from vigia.data_provenance dp
              where dp.entity_type = 'fire_observation' and dp.entity_id = o.id
              order by dp.created_at desc
              limit 1
            ) p on true
            order by o.observed_at desc
            limit :limit
            """
        )
        try:
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement, {"limit": limit})).mappings().all()
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudieron consultar las observaciones.") from exc
        return [dict(row) for row in rows]

    async def latest_ingest_run(self) -> dict[str, Any] | None:
        statement = text(
            """
            select r.state::text, r.started_at, r.finished_at, r.records_received,
                   r.records_written, s.name as source
            from vigia.ingest_runs r
            join vigia.sources s on s.id = r.source_id
            order by r.started_at desc
            limit 1
            """
        )
        try:
            async with self._engine.connect() as connection:
                row = (await connection.execute(statement)).mappings().one_or_none()
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudo consultar la ejecución de workers.") from exc
        return dict(row) if row is not None else None

    async def incidents(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        statement = text(
            """
            select id::text, code, state::text, first_signal_at, last_observation_at,
              observation_count, source_families, evidence_strength::text,
              fusion_data_quality::text as data_quality, stale,
              extensions.st_x(centroid::extensions.geometry) as longitude,
              extensions.st_y(centroid::extensions.geometry) as latitude,
              greatest(0, extract(epoch from (now() - last_observation_at)))::bigint
                as data_age_seconds
            from vigia.fire_incidents
            where public_visible = true
            order by last_observation_at desc, code
            limit :limit
            """
        )
        return await self._mapped_query(
            statement, {"limit": limit}, "No se pudieron consultar los incidentes."
        )

    async def incident(self, incident_id: str) -> dict[str, Any] | None:
        statement = text(
            """
            select id::text, code, state::text, first_signal_at, last_observation_at,
              processed_at, observation_count, source_families, evidence_strength::text,
              reason_codes, explanation, persistence,
              fusion_data_quality::text as data_quality, stale,
              rule_version, configuration_hash,
              extensions.st_x(centroid::extensions.geometry) as longitude,
              extensions.st_y(centroid::extensions.geometry) as latitude
            from vigia.fire_incidents
            where id = cast(:incident_id as uuid) and public_visible = true
            """
        )
        try:
            async with self._engine.connect() as connection:
                row = (
                    (await connection.execute(statement, {"incident_id": incident_id}))
                    .mappings()
                    .one_or_none()
                )
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudo consultar el incidente.") from exc
        return dict(row) if row is not None else None

    async def incident_evidence(self, incident_id: str) -> list[dict[str, Any]]:
        statement = text(
            """
            with public_evidence as (
            select o.id::text as observation_id, evidence.evidence_role as role,
              source.name as source, o.platform, o.sensor, o.observed_at, o.received_at,
              extensions.st_x(o.location::extensions.geometry) as longitude,
              extensions.st_y(o.location::extensions.geometry) as latitude,
              o.confidence_raw, o.frp_mw, o.brightness_kelvin,
              case when provenance.id is null then null else jsonb_build_object(
                'dataset', provenance.dataset,
                'dataset_version', provenance.dataset_version,
                'source_timestamp', provenance.source_timestamp,
                'transformation', provenance.transformation,
                'code_commit', provenance.code_commit,
                'output_hash', provenance.output_hash
              ) end as provenance
            from vigia.observation_evidence evidence
            join vigia.fire_incidents incident on incident.id = evidence.incident_id
              and incident.public_visible = true
            join vigia.fire_observations o on o.id = evidence.observation_id
            join vigia.sources source on source.id = o.source_id
            left join lateral (
              select item.* from vigia.data_provenance item
              where item.entity_type = 'fire_observation' and item.entity_id = o.id
              order by item.created_at desc limit 1
            ) provenance on true
            where evidence.incident_id = cast(:incident_id as uuid)
            union all
            select weather.id::text, context.evidence_role,
              source.name, 'GROUND_STATION', weather.station_code,
              weather.observed_at, weather.received_at,
              extensions.st_x(weather.location::extensions.geometry),
              extensions.st_y(weather.location::extensions.geometry),
              null::text, null::double precision, null::double precision,
              case when provenance.id is null then null else jsonb_build_object(
                'dataset', provenance.dataset,
                'dataset_version', provenance.dataset_version,
                'source_timestamp', provenance.source_timestamp,
                'transformation', provenance.transformation,
                'code_commit', provenance.code_commit,
                'output_hash', provenance.output_hash
              ) end
            from vigia.incident_context_evidence context
            join vigia.fire_incidents incident on incident.id = context.incident_id
              and incident.public_visible = true
            join vigia.weather_observations weather on weather.id = context.entity_id
              and context.entity_type = 'weather_observation'
            join vigia.sources source on source.id = weather.source_id
            left join lateral (
              select item.* from vigia.data_provenance item
              where item.entity_type = 'weather_observation'
                and item.entity_id = weather.id
              order by item.created_at desc limit 1
            ) provenance on true
            where context.incident_id = cast(:incident_id as uuid)
            )
            select * from public_evidence order by observed_at, observation_id
            """
        )
        return await self._mapped_query(
            statement,
            {"incident_id": incident_id},
            "No se pudo consultar la evidencia del incidente.",
        )

    async def incident_history(self, incident_id: str) -> list[dict[str, Any]]:
        statement = text(
            """
            select history.previous_state::text, history.state::text, history.changed_at,
              history.changed_by, history.reason, history.configuration_hash,
              history.software_version, history.rule_version, history.commit_sha
            from vigia.incident_status_history history
            join vigia.fire_incidents incident on incident.id = history.incident_id
              and incident.public_visible = true
            where history.incident_id = cast(:incident_id as uuid)
            order by history.changed_at, history.id
            """
        )
        return await self._mapped_query(
            statement,
            {"incident_id": incident_id},
            "No se pudo consultar el historial del incidente.",
        )

    async def geospatial_layers(self) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select layer, availability::text, count(*)::integer as product_count,
                  max(observed_at) as latest_observed_at,
                  min(output_resolution_m) as finest_resolution_m
                from vigia.geospatial_products
                where invalidated_at is null
                group by layer, availability
                order by layer, availability
                """
            ),
            {},
            "No se pudo consultar el catálogo geoespacial.",
        )

    async def geospatial_coverage(
        self,
        *,
        bbox: tuple[float, float, float, float] | None,
        geometry_geojson: str | None,
        administrative_area: str | None,
        as_of: datetime,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        west, south, east, north = bbox or (None, None, None, None)
        selector = "bbox" if bbox is not None else "geojson" if geometry_geojson else "admin"
        return await self._mapped_query(
            text(
                """
                with query_aoi as (
                  select case
                    when :selector = 'bbox' then extensions.st_makeenvelope(
                      :west, :south, :east, :north, 4326
                    )
                    when :selector = 'geojson' then extensions.st_setsrid(
                      extensions.st_geomfromgeojson(:geometry_geojson), 4326
                    )
                    else (
                      select area.geometry::extensions.geometry
                      from vigia.administrative_areas area
                      where area.external_id = :administrative_area
                         or lower(area.name) = lower(:administrative_area)
                      order by area.dataset_version desc, area.external_id
                      limit 1
                    )
                  end as geometry
                )
                select product.id::text, product.product_id, product.layer,
                  product.availability::text, product.observed_at,
                  product.processed_at, product.output_resolution_m, source.name as source,
                  product.quality, product.is_experimental,
                  product.raster_band, product.value_units, product.render_hint,
                  extensions.st_asgeojson(product.footprint)::jsonb as geometry
                from vigia.geospatial_products product
                join vigia.sources source on source.id = product.source_id
                cross join query_aoi
                where query_aoi.geometry is not null
                  and extensions.st_intersects(product.footprint, query_aoi.geometry)
                  and (product.observed_at is null or product.observed_at <= :as_of)
                  and (product.processed_at is null or product.processed_at <= :as_of)
                  and product.invalidated_at is null
                order by product.observed_at desc nulls last, product.product_id
                limit :limit
                """
            ),
            {
                "west": west,
                "south": south,
                "east": east,
                "north": north,
                "selector": selector,
                "geometry_geojson": geometry_geojson,
                "administrative_area": administrative_area,
                "as_of": as_of,
                "limit": limit,
            },
            "No se pudo consultar la cobertura geoespacial.",
        )

    async def geospatial_context(
        self, *, longitude: float, latitude: float, as_of: datetime
    ) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select distinct on (product.layer)
                  product.id::text, product.product_id, product.layer,
                  product.availability::text, product.observed_at, product.processed_at,
                  product.output_resolution_m, product.quality, product.provenance_id::text,
                  product.storage_uri, product.raster_band, product.value_units,
                  product.render_hint, source.name as source,
                  case when product.layer = 'LAND_COVER' then (
                    select jsonb_build_object(
                      'class_code', feature.class_code,
                      'class_uri', feature.class_uri,
                      'covered_percentage', feature.covered_percentage,
                      'observed_at', feature.observed_at
                    )
                    from vigia.land_cover_features feature
                    where feature.product_id = product.id
                      and extensions.st_covers(
                        feature.geometry,
                        extensions.st_setsrid(
                          extensions.st_makepoint(:longitude, :latitude), 4326
                        )
                      )
                    order by feature.covered_percentage desc nulls last, feature.external_id
                    limit 1
                  ) else null end as vector_value
                from vigia.geospatial_products product
                join vigia.sources source on source.id = product.source_id
                where extensions.st_covers(
                  product.footprint,
                  extensions.st_setsrid(
                    extensions.st_makepoint(:longitude, :latitude), 4326
                  )
                )
                  and (product.observed_at is null or product.observed_at <= :as_of)
                  and (product.processed_at is null or product.processed_at <= :as_of)
                  and product.invalidated_at is null
                order by product.layer, product.observed_at desc nulls last
                """
            ),
            {"longitude": longitude, "latitude": latitude, "as_of": as_of},
            "No se pudo consultar el contexto geoespacial.",
        )

    async def administrative_context(
        self, *, longitude: float, latitude: float, as_of: datetime
    ) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select area.external_id, area.name, area.level::text,
                  area.dataset_version, area.valid_from, area.valid_to,
                  area.created_at as retrieved_at, area.provenance_id::text,
                  source.name as source
                from vigia.administrative_areas area
                join vigia.sources source on source.id = area.source_id
                where extensions.st_covers(
                  area.geometry,
                  extensions.st_setsrid(
                    extensions.st_makepoint(:longitude, :latitude), 4326
                  )
                )
                  and (area.valid_from is null or area.valid_from <= :as_of)
                  and (area.valid_to is null or area.valid_to > :as_of)
                order by case area.level
                  when 'COUNTRY' then 1
                  when 'AUTONOMOUS_COMMUNITY' then 2
                  when 'PROVINCE' then 3
                  when 'MUNICIPALITY' then 4
                  else 5 end
                """
            ),
            {"longitude": longitude, "latitude": latitude, "as_of": as_of},
            "No se pudo resolver la administración territorial.",
        )

    async def geospatial_product(self, product_id: str) -> dict[str, Any] | None:
        try:
            async with self._engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                """
                            select id::text, product_id, layer, availability::text,
                              storage_uri, raster_band, value_units, render_hint
                            from vigia.geospatial_products
                            where id = cast(:product_id as uuid)
                              and availability in ('AVAILABLE', 'PARTIAL')
                              and invalidated_at is null
                            """
                            ),
                            {"product_id": product_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudo consultar el producto geoespacial.") from exc
        return dict(row) if row is not None else None

    async def risk_current(
        self, *, longitude: float, latitude: float, as_of: datetime
    ) -> dict[str, Any] | None:
        statement = text(
            """
            select prediction.id::text, prediction.mode::text, prediction.as_of,
              prediction.valid_at, prediction.horizon_hours,
              prediction.experimental_index, prediction.risk_class,
              run.data_quality::text as data_quality,
              prediction.component_scores, prediction.component_details,
              prediction.reason_codes, prediction.explanations,
              prediction.missing_components, prediction.input_resolutions,
              prediction.engine_version, prediction.raster_product_id::text,
              prediction.provenance_id::text
            from vigia.risk_predictions prediction
            join vigia.risk_runs run on run.id = prediction.run_id
            where run.state = 'SUCCEEDED' and prediction.mode = 'ANALYSIS'
              and prediction.as_of <= :as_of and prediction.valid_at <= :as_of
              and extensions.st_covers(
                prediction.geometry,
                extensions.st_setsrid(
                  extensions.st_makepoint(:longitude, :latitude), 4326
                )
              )
            order by prediction.valid_at desc, prediction.created_at desc
            limit 1
            """
        )
        try:
            async with self._engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            statement,
                            {"longitude": longitude, "latitude": latitude, "as_of": as_of},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudo consultar el riesgo actual.") from exc
        return dict(row) if row is not None else None

    async def risk_forecast(
        self,
        *,
        longitude: float,
        latitude: float,
        as_of: datetime,
        max_horizon_hours: int,
    ) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select distinct on (prediction.valid_at)
                  prediction.id::text, prediction.mode::text, prediction.as_of,
                  prediction.valid_at, prediction.horizon_hours,
                  prediction.experimental_index, prediction.risk_class,
                  run.data_quality::text as data_quality,
                  prediction.component_scores, prediction.component_details,
                  prediction.reason_codes, prediction.explanations,
                  prediction.missing_components, prediction.input_resolutions,
                  prediction.engine_version, prediction.raster_product_id::text,
                  prediction.provenance_id::text
                from vigia.risk_predictions prediction
                join vigia.risk_runs run on run.id = prediction.run_id
                where run.state = 'SUCCEEDED' and prediction.mode = 'FORECAST'
                  and prediction.as_of <= :as_of and prediction.valid_at >= :as_of
                  and prediction.horizon_hours <= :max_horizon_hours
                  and extensions.st_covers(
                    prediction.geometry,
                    extensions.st_setsrid(
                      extensions.st_makepoint(:longitude, :latitude), 4326
                    )
                  )
                order by prediction.valid_at, prediction.as_of desc, prediction.created_at desc
                """
            ),
            {
                "longitude": longitude,
                "latitude": latitude,
                "as_of": as_of,
                "max_horizon_hours": max_horizon_hours,
            },
            "No se pudo consultar el pronóstico de riesgo.",
        )

    async def risk_layers(self) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select product.id::text, product.product_id, product.layer,
                  product.availability::text, product.observed_at, product.processed_at,
                  product.output_resolution_m, product.raster_band, product.value_units,
                  product.render_hint, product.quality, source.name as source
                from vigia.geospatial_products product
                join vigia.sources source on source.id = product.source_id
                where product.layer in ('RISK_BASELINE', 'FWI', 'RISK_DATA_QUALITY')
                  and product.invalidated_at is null
                order by product.observed_at desc nulls last, product.layer
                """
            ),
            {},
            "No se pudieron consultar las capas de riesgo.",
        )

    async def replay_cases(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select case_row.id::text, case_row.case_key, case_row.kind::text,
                  case_row.replay_start, case_row.replay_end, case_row.time_step_minutes,
                  case_row.case_version, case_row.reference_quality::text,
                  case_row.available_sources, case_row.reference_sources,
                  case_row.sensor_availability, case_row.manifest_hash,
                  fire.vigia_code as historical_event_code, fire.name,
                  fire.region, fire.provinces, fire.municipality,
                  fire.started_at as official_start_time,
                  extensions.st_x(fire.origin::extensions.geometry) as reference_longitude,
                  extensions.st_y(fire.origin::extensions.geometry) as reference_latitude,
                  count(input.id)::integer as input_count
                from vigia.replay_cases case_row
                left join vigia.historical_fires fire on fire.id = case_row.historical_fire_id
                left join vigia.replay_inputs input on input.case_id = case_row.id
                group by case_row.id, fire.id
                order by case_row.replay_start desc, case_row.case_key
                limit :limit
                """
            ),
            {"limit": limit},
            "No se pudieron consultar los casos replay.",
        )

    async def replay_case(self, case_id: str) -> dict[str, Any] | None:
        statement = text(
            """
            select case_row.id::text, case_row.case_key, case_row.kind::text,
              case_row.replay_start, case_row.replay_end, case_row.time_step_minutes,
              case_row.manifest, case_row.manifest_hash, case_row.case_version,
              case_row.selection_policy_version, case_row.available_sources,
              case_row.reference_sources, case_row.sensor_availability,
              case_row.reference_quality::text, case_row.frozen,
              extensions.st_asgeojson(case_row.aoi)::jsonb as aoi,
              fire.event_key as historical_fire_event_id,
              fire.vigia_code as historical_event_code, fire.name,
              fire.region, fire.provinces, fire.municipality,
              fire.started_at as official_start_time,
              extensions.st_x(fire.origin::extensions.geometry) as reference_longitude,
              extensions.st_y(fire.origin::extensions.geometry) as reference_latitude,
              coalesce((
                select jsonb_agg(jsonb_build_object(
                  'meaning', timestamp_row.meaning,
                  'instant', timestamp_row.instant,
                  'calendar_date', timestamp_row.calendar_date,
                  'precision', timestamp_row.precision::text,
                  'timezone', timestamp_row.timezone_name
                ) order by timestamp_row.meaning, timestamp_row.instant)
                from vigia.historical_fire_references reference
                join vigia.historical_fire_timestamps timestamp_row
                  on timestamp_row.reference_id = reference.id
                where reference.historical_fire_id = fire.id
              ), '[]'::jsonb) as reference_timestamps,
              coalesce((
                select jsonb_agg(jsonb_build_object(
                  'source', source.name,
                  'provider', source.provider,
                  'retrieved_at', reference.retrieved_at,
                  'quality', reference.reference_quality::text,
                  'source_uri', reference.source_uri,
                  'license_uri', reference.license_uri
                ) order by reference.retrieved_at, reference.id)
                from vigia.historical_fire_references reference
                join vigia.sources source on source.id = reference.source_id
                where reference.historical_fire_id = fire.id
              ), '[]'::jsonb) as references,
              coalesce((
                select jsonb_agg(jsonb_build_object(
                  'external_id', perimeter.external_id,
                  'reference_at', perimeter.reference_at,
                  'reference_date', perimeter.reference_date,
                  'precision', perimeter.temporal_precision::text,
                  'area_ha', perimeter.area_ha,
                  'geometry', extensions.st_asgeojson(perimeter.geometry)::jsonb
                ) order by perimeter.reference_at nulls last, perimeter.id)
                from vigia.historical_fire_perimeters perimeter
                where perimeter.historical_fire_id = fire.id
              ), '[]'::jsonb) as reference_perimeters
            from vigia.replay_cases case_row
            left join vigia.historical_fires fire on fire.id = case_row.historical_fire_id
            where case_row.id::text = :case_id or case_row.case_key = :case_id
            limit 1
            """
        )
        try:
            async with self._engine.connect() as connection:
                row = (
                    (await connection.execute(statement, {"case_id": case_id}))
                    .mappings()
                    .one_or_none()
                )
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudo consultar el caso replay.") from exc
        return dict(row) if row is not None else None

    async def replay_inputs(self, case_id: str) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select input.input_key as input_id, input.kind::text as kind,
                  input.source_code as source, input.observed_at, input.available_at,
                  extensions.st_x(input.location::extensions.geometry) as longitude,
                  extensions.st_y(input.location::extensions.geometry) as latitude,
                  input.payload, input.provenance, input.availability_basis,
                  input.quality_flags
                from vigia.replay_inputs input
                join vigia.replay_cases case_row on case_row.id = input.case_id
                where case_row.id::text = :case_id or case_row.case_key = :case_id
                order by input.observed_at, input.input_key
                """
            ),
            {"case_id": case_id},
            "No se pudieron consultar los inputs replay.",
        )

    async def replay_run(self, run_id: str) -> dict[str, Any] | None:
        statement = text(
            """
            select run.id::text, run.run_hash, run.state::text, run.code_commit,
              run.engine_versions, run.configuration_hash, run.case_manifest_hash,
              run.started_at, run.completed_at, run.step_count, run.completed_step,
              run.observations_processed, run.wall_time_ms,
              run.approximate_peak_memory_bytes, run.deterministic,
              run.live_state_mutated, run.errors,
              case_row.id::text as case_id, case_row.case_key
            from vigia.replay_runs run
            join vigia.replay_cases case_row on case_row.id = run.case_id
            where run.id::text = :run_id or run.run_hash = :run_id
            limit 1
            """
        )
        try:
            async with self._engine.connect() as connection:
                row = (
                    (await connection.execute(statement, {"run_id": run_id}))
                    .mappings()
                    .one_or_none()
                )
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudo consultar ReplayRun.") from exc
        return dict(row) if row is not None else None

    async def replay_timeline(self, run_id: str) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select step.step_index, step.as_of, step.visible_input_count,
                  step.visible_observation_count, step.candidate_count,
                  step.incidents, step.risk, step.availability,
                  step.exclusion_counts, step.output_hash
                from vigia.replay_steps step
                join vigia.replay_runs run on run.id = step.replay_run_id
                where run.id::text = :run_id or run.run_hash = :run_id
                order by step.step_index
                """
            ),
            {"run_id": run_id},
            "No se pudo consultar la timeline replay.",
        )

    async def replay_incidents(self, run_id: str) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select step.step_index, step.as_of, incident.value as incident
                from vigia.replay_steps step
                join vigia.replay_runs run on run.id = step.replay_run_id
                cross join lateral jsonb_array_elements(step.incidents) incident(value)
                where run.id::text = :run_id or run.run_hash = :run_id
                order by step.step_index, incident.value->>'replay_incident_id'
                """
            ),
            {"run_id": run_id},
            "No se pudieron consultar los incidentes replay.",
        )

    async def replay_observations(
        self, run_id: str, *, as_of: datetime, limit: int
    ) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select input.input_key as id, input.source_code as source,
                  input.observed_at, input.available_at,
                  extensions.st_x(input.location::extensions.geometry) as longitude,
                  extensions.st_y(input.location::extensions.geometry) as latitude,
                  input.payload->>'platform' as platform,
                  input.payload->>'sensor' as sensor,
                  input.payload->>'confidence_raw' as confidence_raw,
                  input.payload->'frp_mw' as frp_mw,
                  input.availability_basis, input.quality_flags
                from vigia.replay_inputs input
                join vigia.replay_runs run on run.case_id = input.case_id
                where (run.id::text = :run_id or run.run_hash = :run_id)
                  and input.kind = 'THERMAL_OBSERVATION'
                  and input.observed_at <= :as_of
                  and input.available_at <= :as_of
                  and input.location is not null
                order by input.observed_at, input.input_key
                limit :limit
                """
            ),
            {"run_id": run_id, "as_of": as_of, "limit": limit},
            "No se pudieron consultar las observaciones Replay.",
        )

    async def validation_datasets(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select dataset.id::text, dataset.version, dataset.dataset_hash,
                  dataset.event_count, dataset.control_count, dataset.regions_covered,
                  dataset.years_covered, dataset.coverage_limitations,
                  dataset.selection_policy_version, dataset.frozen,
                  dataset.created_at, dataset.published_at,
                  split.id::text as split_id, split.version as split_version,
                  split.split_hash, split.development_count, split.validation_count,
                  split.test_count, split.test_frozen, split.leakage_checked
                from vigia.validation_dataset_versions dataset
                left join lateral (
                  select candidate.* from vigia.validation_split_manifests candidate
                  where candidate.dataset_version_id = dataset.id
                  order by candidate.created_at desc limit 1
                ) split on true
                order by dataset.created_at desc
                limit :limit
                """
            ),
            {"limit": limit},
            "No se pudieron consultar los datasets de validación.",
        )

    async def validation_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        statement = text(
            """
            select dataset.id::text, dataset.version, dataset.dataset_hash,
              dataset.manifest, dataset.sources, dataset.filters,
              dataset.selection_policy_version, dataset.event_count,
              dataset.control_count, dataset.regions_covered, dataset.years_covered,
              dataset.coverage_limitations, dataset.frozen,
              dataset.created_at, dataset.published_at
            from vigia.validation_dataset_versions dataset
            where dataset.id::text = :dataset_id or dataset.version = :dataset_id
              or dataset.dataset_hash = :dataset_id
            """
        )
        try:
            async with self._engine.connect() as connection:
                row = (
                    (await connection.execute(statement, {"dataset_id": dataset_id}))
                    .mappings()
                    .one_or_none()
                )
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError(
                "No se pudo consultar el dataset de validación."
            ) from exc
        return dict(row) if row is not None else None

    async def validation_runs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select run.id::text, run.run_key, run.started_at, run.completed_at,
                  run.commit_sha, run.dataset_hash, run.split_role::text,
                  run.matcher_version, run.matcher_configuration_hash,
                  run.configuration_hash, run.sample_counts,
                  run.eligibility_counts, run.excluded_counts, run.limitations,
                  run.unavailable_metrics, run.report_hash, run.published,
                  run.reproducible, run.live_state_mutated,
                  dataset.version as dataset_version,
                  split.version as split_version,
                  engine.name as engine_version
                from vigia.validation_runs run
                join vigia.validation_dataset_versions dataset
                  on dataset.id = run.dataset_version_id
                join vigia.validation_split_manifests split
                  on split.id = run.split_manifest_id
                join vigia.validation_engine_versions engine
                  on engine.id = run.engine_version_id
                where run.run_key is not null
                order by run.started_at desc
                limit :limit
                """
            ),
            {"limit": limit},
            "No se pudieron consultar los ValidationRuns.",
        )

    async def validation_run(self, run_id: str) -> dict[str, Any] | None:
        statement = text(
            """
            select run.id::text, run.run_key, run.report, run.report_hash,
              run.started_at, run.completed_at, run.commit_sha,
              run.split_role::text, run.reproducible, run.published,
              run.live_state_mutated, dataset.version as dataset_version,
              dataset.dataset_hash, split.version as split_version,
              split.split_hash, engine.name as engine_version
            from vigia.validation_runs run
            join vigia.validation_dataset_versions dataset
              on dataset.id = run.dataset_version_id
            join vigia.validation_split_manifests split
              on split.id = run.split_manifest_id
            join vigia.validation_engine_versions engine
              on engine.id = run.engine_version_id
            where run.id::text = :run_id or run.run_key = :run_id
              or run.report_hash = :run_id
            """
        )
        try:
            async with self._engine.connect() as connection:
                row = (
                    (await connection.execute(statement, {"run_id": run_id}))
                    .mappings()
                    .one_or_none()
                )
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudo consultar ValidationRun.") from exc
        return dict(row) if row is not None else None

    async def validation_metrics(self, run_id: str) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select metric.metric_name, metric.availability::text, metric.unit,
                  metric.population, metric.sample_size as n, metric.numerator,
                  metric.denominator, metric.metric_value as value,
                  metric.confidence_interval, metric.subgroup, metric.reason,
                  metric.limitations
                from vigia.validation_metric_results metric
                join vigia.validation_runs run on run.id = metric.validation_run_id
                where run.id::text = :run_id or run.run_key = :run_id
                order by metric.metric_name, metric.subgroup::text
                """
            ),
            {"run_id": run_id},
            "No se pudieron consultar las métricas de validación.",
        )

    async def validation_errors(self, run_id: str) -> list[dict[str, Any]]:
        return await self._mapped_query(
            text(
                """
                select error.id::text, error.member_key, error.replay_incident_key,
                  error.reason_codes, error.evidence, error.manual_override,
                  error.created_at
                from vigia.validation_errors error
                join vigia.validation_runs run on run.id = error.validation_run_id
                where run.id::text = :run_id or run.run_key = :run_id
                order by error.created_at, error.id
                """
            ),
            {"run_id": run_id},
            "No se pudieron consultar los errores de validación.",
        )

    async def _mapped_query(
        self, statement: Any, parameters: dict[str, Any], safe_error: str
    ) -> list[dict[str, Any]]:
        try:
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement, parameters)).mappings().all()
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError(safe_error) from exc
        return [dict(row) for row in rows]
