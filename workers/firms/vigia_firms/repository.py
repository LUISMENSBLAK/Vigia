import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from services.api.vigia_api.database import VigiaDatabase

from .client import FirmsObservation, raw_input_hash


class FirmsPersistenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IngestRun:
    id: UUID
    source_id: UUID
    started_at: datetime


@dataclass(frozen=True, slots=True)
class IngestResult:
    records_received: int
    records_written: int


def configuration_hash(
    *, source: str, bbox: tuple[float, float, float, float], day_range: int
) -> str:
    configuration = {"source": source, "bbox": bbox, "day_range": day_range}
    canonical = json.dumps(configuration, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _output_hash(observation: FirmsObservation) -> str:
    output = {
        "external_id": observation.external_id,
        "latitude": observation.latitude,
        "longitude": observation.longitude,
        "observed_at": observation.acquired_at.isoformat(),
        "received_at": observation.received_at.isoformat(),
        "satellite": observation.satellite,
        "instrument": observation.instrument,
        "confidence": observation.confidence,
        "brightness": observation.brightness,
        "frp": observation.frp,
        "daynight": observation.daynight,
    }
    canonical = json.dumps(output, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class FirmsRepository:
    def __init__(self, database: VigiaDatabase) -> None:
        self._database = database

    async def begin_run(
        self,
        *,
        source_code: str,
        software_version: str,
        configuration_hash_value: str,
        request_id: str,
        started_at: datetime,
    ) -> IngestRun:
        statement = text(
            """
            insert into vigia.ingest_runs (
              source_id, state, started_at, software_version, request_id, configuration_hash
            )
            select id, 'RUNNING', :started_at, :software_version, :request_id, :configuration_hash
            from vigia.sources
            where code = :source_code
            returning id, source_id, started_at
            """
        )
        async with self._database.transaction() as connection:
            row = (
                await connection.execute(
                    statement,
                    {
                        "source_code": source_code,
                        "started_at": started_at,
                        "software_version": software_version,
                        "request_id": request_id,
                        "configuration_hash": configuration_hash_value,
                    },
                )
            ).mappings().one_or_none()
        if row is None:
            raise FirmsPersistenceError(
                f"La fuente {source_code} no existe; aplica la migración inicial de VIGÍA."
            )
        return IngestRun(id=row["id"], source_id=row["source_id"], started_at=row["started_at"])

    async def persist(
        self,
        run: IngestRun,
        observations: list[FirmsObservation],
        *,
        code_commit: str,
        finished_at: datetime,
    ) -> IngestResult:
        payload = [
            {
                "external_id": observation.external_id,
                "observed_at": observation.acquired_at.isoformat(),
                "received_at": observation.received_at.isoformat(),
                "longitude": observation.longitude,
                "latitude": observation.latitude,
                "sensor": observation.instrument,
                "platform": observation.satellite,
                "confidence_raw": observation.confidence,
                "brightness_kelvin": observation.brightness,
                "frp_mw": observation.frp,
                "daynight": observation.daynight,
                "raw_properties": observation.raw_properties,
            }
            for observation in observations
        ]
        insert_observations = text(
            """
            with input as (
              select *
              from jsonb_to_recordset(cast(:payload as jsonb)) as x(
                external_id text,
                observed_at timestamptz,
                received_at timestamptz,
                longitude double precision,
                latitude double precision,
                sensor text,
                platform text,
                confidence_raw text,
                brightness_kelvin double precision,
                frp_mw double precision,
                daynight text,
                raw_properties jsonb
              )
            )
            insert into vigia.fire_observations (
              source_id, ingest_run_id, external_id, observed_at, received_at, location,
              sensor, platform, confidence_raw, brightness_kelvin, frp_mw, daynight,
              quality, raw_properties
            )
            select
              :source_id, :ingest_run_id, external_id, observed_at, received_at,
              extensions.st_setsrid(
                extensions.st_makepoint(longitude, latitude), 4326
              )::extensions.geography,
              sensor, platform, confidence_raw, brightness_kelvin, frp_mw, daynight,
              '{}'::jsonb, raw_properties
            from input
            on conflict (source_id, external_id) do nothing
            returning id, external_id
            """
        )
        update_run = text(
            """
            update vigia.ingest_runs
            set state = 'SUCCEEDED', finished_at = :finished_at,
                records_received = :records_received, records_written = :records_written
            where id = :ingest_run_id
            """
        )
        update_health = text(
            """
            insert into vigia.source_health (
              source_id, state, checked_at, last_observed_at, last_received_at,
              latency_seconds, error_code, detail, last_success_at,
              last_product_at, last_ingest_at, check_interval_seconds,
              product_freshness_seconds
            )
            values (
              :source_id, cast(:state as vigia.source_state), :checked_at,
              :last_observed_at, :last_received_at, :latency_seconds, null, :detail,
              :checked_at, :last_observed_at, :last_received_at, 21600, 43200
            )
            on conflict (source_id) do update set
              state = excluded.state,
              checked_at = excluded.checked_at,
              last_success_at = excluded.last_success_at,
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
              latency_seconds = coalesce(
                excluded.latency_seconds, vigia.source_health.latency_seconds
              ),
              check_interval_seconds = excluded.check_interval_seconds,
              product_freshness_seconds = excluded.product_freshness_seconds,
              error_code = null,
              detail = excluded.detail
            """
        )

        async with self._database.transaction() as connection:
            inserted_rows: list[dict[str, Any]] = []
            if payload:
                result = await connection.execute(
                    insert_observations,
                    {
                        "payload": json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                        "source_id": run.source_id,
                        "ingest_run_id": run.id,
                    },
                )
                inserted_rows = [dict(row) for row in result.mappings().all()]

            by_external_id = {item.external_id: item for item in observations}
            provenance_rows = [
                {
                    "entity_id": row["id"],
                    "dataset": observation.source.value,
                    "source_timestamp": observation.acquired_at,
                    "code_commit": code_commit,
                    "parameters": json.dumps(
                        {"parser": "firms_area_csv_v1"}, separators=(",", ":"), sort_keys=True
                    ),
                    "input_hashes": [raw_input_hash(observation)],
                    "output_hash": _output_hash(observation),
                }
                for row in inserted_rows
                for observation in [by_external_id[row["external_id"]]]
            ]
            if provenance_rows:
                await connection.execute(
                    text(
                        """
                        insert into vigia.data_provenance (
                          entity_type, entity_id, dataset, dataset_version, source_timestamp,
                          transformation, code_commit, parameters, input_hashes, output_hash
                        ) values (
                          'fire_observation', :entity_id, :dataset,
                          'not_specified_by_firms_area_csv', :source_timestamp,
                          'firms_area_csv_v1', :code_commit, cast(:parameters as jsonb),
                          :input_hashes, :output_hash
                        )
                        """
                    ),
                    provenance_rows,
                )

            await connection.execute(
                update_run,
                {
                    "finished_at": finished_at,
                    "records_received": len(observations),
                    "records_written": len(inserted_rows),
                    "ingest_run_id": run.id,
                },
            )
            latest = max(observations, key=lambda item: item.acquired_at) if observations else None
            latency = (
                max(0, int((latest.received_at - latest.acquired_at).total_seconds()))
                if latest is not None
                else None
            )
            await connection.execute(
                update_health,
                {
                    "source_id": run.source_id,
                    "state": "OPERATIVO",
                    "checked_at": finished_at,
                    "last_observed_at": latest.acquired_at if latest else None,
                    "last_received_at": latest.received_at if latest else None,
                    "latency_seconds": latency,
                    "detail": (
                        "Llamada FIRMS correcta y observaciones persistidas."
                        if observations
                        else "Llamada FIRMS correcta sin observaciones para la ventana solicitada."
                    ),
                },
            )
        return IngestResult(records_received=len(observations), records_written=len(inserted_rows))

    async def fail(
        self,
        run: IngestRun,
        *,
        error_code: str,
        detail: str,
        degraded: bool,
        finished_at: datetime | None = None,
    ) -> None:
        completed_at = finished_at or datetime.now(UTC)
        async with self._database.transaction() as connection:
            await connection.execute(
                text(
                    """
                    update vigia.ingest_runs
                    set state = 'FAILED', finished_at = :finished_at,
                        errors = cast(:errors as jsonb)
                    where id = :ingest_run_id
                    """
                ),
                {
                    "finished_at": completed_at,
                    "errors": json.dumps([{"code": error_code, "detail": detail}]),
                    "ingest_run_id": run.id,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into vigia.source_health (
                      source_id, state, checked_at, error_code, detail
                    ) values (
                      :source_id, cast(:state as vigia.source_state), :checked_at,
                      :error_code, :detail
                    )
                    on conflict (source_id) do update set
                      state = excluded.state,
                      checked_at = excluded.checked_at,
                      error_code = excluded.error_code,
                      detail = excluded.detail
                    """
                ),
                {
                    "source_id": run.source_id,
                    "state": "DEGRADADO" if degraded else "ERROR",
                    "checked_at": completed_at,
                    "error_code": error_code,
                    "detail": detail,
                },
            )
