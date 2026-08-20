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
                postgis_version = await connection.scalar(text("select postgis_version()"))
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError("No se pudo verificar Supabase/PostGIS.") from exc
        if not isinstance(postgis_version, str):
            raise DatabaseUnavailableError("PostGIS no devolvió una versión verificable.")
        return DatabaseHealth(checked_at=datetime.now(UTC), postgis_version=postgis_version)

    async def source_health(self) -> list[dict[str, Any]]:
        statement = text(
            """
            select code, name, state::text, checked_at, last_observed_at, last_received_at,
                   latency_seconds, error_code, detail
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
                    await connection.execute(statement, {"incident_id": incident_id})
                ).mappings().one_or_none()
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

    async def _mapped_query(
        self, statement: Any, parameters: dict[str, Any], safe_error: str
    ) -> list[dict[str, Any]]:
        try:
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement, parameters)).mappings().all()
        except (SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailableError(safe_error) from exc
        return [dict(row) for row in rows]
