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
              o.platform as satellite,
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
