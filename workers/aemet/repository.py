import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from services.api.vigia_api.database import VigiaDatabase

from .client import AemetObservation


@dataclass(frozen=True, slots=True)
class AemetIngestRun:
    id: UUID
    source_id: UUID


class AemetRepository:
    source_code = "AEMET_OPEN_DATA"

    def __init__(self, database: VigiaDatabase) -> None:
        self._database = database

    async def begin_run(
        self,
        *,
        started_at: datetime,
        request_id: str,
        software_version: str,
        configuration_hash: str,
    ) -> AemetIngestRun:
        async with self._database.transaction() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        insert into vigia.ingest_runs (
                          source_id, state, started_at, software_version,
                          request_id, configuration_hash
                        )
                        select id, 'RUNNING', :started_at, :software_version,
                               :request_id, :configuration_hash
                        from vigia.sources where code = :source_code
                        returning id, source_id
                        """
                    ),
                    {
                        "started_at": started_at,
                        "software_version": software_version,
                        "request_id": request_id,
                        "configuration_hash": configuration_hash,
                        "source_code": self.source_code,
                    },
                )
            ).mappings().one()
        return AemetIngestRun(id=row["id"], source_id=row["source_id"])

    async def persist(
        self,
        run: AemetIngestRun,
        observations: list[AemetObservation],
        *,
        code_commit: str,
        finished_at: datetime,
    ) -> int:
        payload = [
            {
                "external_id": item.external_id,
                "station_code": item.station_code,
                "observed_at": item.observed_at.isoformat(),
                "received_at": item.received_at.isoformat(),
                "longitude": item.longitude,
                "latitude": item.latitude,
                "value_type": item.value_type,
                "temperature_c": item.temperature_c,
                "relative_humidity_pct": item.relative_humidity_pct,
                "wind_speed_ms": item.wind_speed_ms,
                "wind_direction_deg": item.wind_direction_deg,
                "gust_ms": item.gust_ms,
                "precipitation_mm": item.precipitation_mm,
                "pressure_hpa": item.pressure_hpa,
                "quality": item.quality,
                "raw_properties": item.raw_properties,
            }
            for item in observations
        ]
        async with self._database.transaction() as connection:
            inserted: list[dict[str, object]] = []
            if payload:
                result = await connection.execute(
                    text(
                        """
                        with input as (
                          select * from jsonb_to_recordset(cast(:payload as jsonb)) as x(
                            external_id text, station_code text, observed_at timestamptz,
                            received_at timestamptz, longitude double precision,
                            latitude double precision, value_type text,
                            temperature_c double precision, relative_humidity_pct double precision,
                            wind_speed_ms double precision, wind_direction_deg double precision,
                            gust_ms double precision, precipitation_mm double precision,
                            pressure_hpa double precision, quality jsonb, raw_properties jsonb
                          )
                        )
                        insert into vigia.weather_observations (
                          source_id, ingest_run_id, external_id, station_code,
                          observed_at, received_at, location, value_type,
                          temperature_c, relative_humidity_pct, wind_speed_ms,
                          wind_direction_deg, gust_ms, precipitation_mm, pressure_hpa,
                          quality, raw_properties
                        )
                        select :source_id, :ingest_run_id, external_id, station_code,
                          observed_at, received_at,
                          extensions.st_setsrid(
                            extensions.st_makepoint(longitude, latitude), 4326
                          )::extensions.geography,
                          cast(value_type as vigia.weather_value_type), temperature_c,
                          relative_humidity_pct, wind_speed_ms, wind_direction_deg,
                          gust_ms, precipitation_mm, pressure_hpa, quality, raw_properties
                        from input
                        on conflict (source_id, external_id) do nothing
                        returning id, external_id
                        """
                    ),
                    {
                        "payload": json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                        "source_id": run.source_id,
                        "ingest_run_id": run.id,
                    },
                )
                inserted = [dict(row) for row in result.mappings().all()]

            by_id = {item.external_id: item for item in observations}
            output_by_id = {str(item["external_id"]): item for item in payload}
            provenance = []
            for row in inserted:
                observation = by_id[str(row["external_id"])]
                raw = json.dumps(
                    observation.raw_properties,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                provenance.append(
                    {
                        "entity_id": row["id"],
                        "source_timestamp": observation.observed_at,
                        "code_commit": code_commit,
                        "input_hashes": [hashlib.sha256(raw.encode()).hexdigest()],
                        "output_hash": hashlib.sha256(
                            json.dumps(
                                output_by_id[observation.external_id],
                                ensure_ascii=True,
                                separators=(",", ":"),
                                sort_keys=True,
                            ).encode()
                        ).hexdigest(),
                    }
                )
            if provenance:
                await connection.execute(
                    text(
                        """
                        insert into vigia.data_provenance (
                          entity_type, entity_id, dataset, dataset_version, source_timestamp,
                          transformation, code_commit, parameters, input_hashes, output_hash
                        ) values (
                          'weather_observation', :entity_id, 'AEMET OpenData',
                          'not_specified_by_observation_endpoint', :source_timestamp,
                          'aemet_conventional_observation_v1', :code_commit,
                          '{"value_type":"OBSERVADO"}'::jsonb, :input_hashes, :output_hash
                        )
                        """
                    ),
                    provenance,
                )

            latest = max(observations, key=lambda item: item.observed_at) if observations else None
            latency = (
                max(0, int((latest.received_at - latest.observed_at).total_seconds()))
                if latest
                else None
            )
            await connection.execute(
                text(
                    """
                    update vigia.ingest_runs set state = 'SUCCEEDED', finished_at = :finished_at,
                      records_received = :received, records_written = :written
                    where id = :run_id
                    """
                ),
                {
                    "finished_at": finished_at,
                    "received": len(observations),
                    "written": len(inserted),
                    "run_id": run.id,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into vigia.source_health (
                      source_id, state, checked_at, last_observed_at, last_received_at,
                      latency_seconds, detail
                    ) values (
                      :source_id, cast(:health_state as vigia.source_state), :finished_at,
                      :observed_at, :received_at, :latency,
                      :detail
                    ) on conflict (source_id) do update set
                      state = excluded.state, checked_at = excluded.checked_at,
                      last_observed_at = coalesce(
                        excluded.last_observed_at, vigia.source_health.last_observed_at
                      ),
                      last_received_at = coalesce(
                        excluded.last_received_at, vigia.source_health.last_received_at
                      ),
                      latency_seconds = coalesce(
                        excluded.latency_seconds, vigia.source_health.latency_seconds
                      ),
                      error_code = null, detail = excluded.detail
                    """
                ),
                {
                    "finished_at": finished_at,
                    "source_id": run.source_id,
                    "health_state": "OPERATIVO",
                    "observed_at": latest.observed_at if latest else None,
                    "received_at": latest.received_at if latest else None,
                    "latency": latency,
                    "detail": (
                        "Llamada AEMET correcta y observaciones persistidas."
                        if observations
                        else "Llamada AEMET correcta sin observaciones disponibles."
                    ),
                },
            )
        return len(inserted)

    async def fail(
        self,
        run: AemetIngestRun,
        *,
        error_code: str,
        detail: str,
        finished_at: datetime,
    ) -> None:
        async with self._database.transaction() as connection:
            await connection.execute(
                text(
                    """
                    update vigia.ingest_runs set state = 'FAILED', finished_at = :finished_at,
                      errors = cast(:errors as jsonb)
                    where id = :run_id
                    """
                ),
                {
                    "finished_at": finished_at,
                    "errors": json.dumps([{"code": error_code, "detail": detail}]),
                    "run_id": run.id,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into vigia.source_health (
                      source_id, state, checked_at, error_code, detail
                    ) values (
                      :source_id, 'ERROR', :finished_at, :error_code, :detail
                    ) on conflict (source_id) do update set
                      state = excluded.state, checked_at = excluded.checked_at,
                      error_code = excluded.error_code, detail = excluded.detail
                    """
                ),
                {
                    "source_id": run.source_id,
                    "finished_at": finished_at,
                    "error_code": error_code,
                    "detail": detail,
                },
            )
