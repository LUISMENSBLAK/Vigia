from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text

from services.api.vigia_api.database import VigiaDatabase

from .models import RiskAssessment


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


class RiskRepository:
    def __init__(self, database: VigiaDatabase) -> None:
        self._database = database

    async def observed_weather_stations(
        self,
        *,
        longitude: float,
        latitude: float,
        as_of: datetime,
        max_age: timedelta,
        max_distance_km: float,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        statement = text(
            """
            select distinct on (observation.station_code)
              observation.station_code, observation.observed_at,
              extensions.st_y(observation.location::extensions.geometry) as latitude,
              extensions.st_x(observation.location::extensions.geometry) as longitude,
              observation.temperature_c, observation.relative_humidity_pct,
              observation.wind_speed_ms, observation.gust_ms,
              observation.precipitation_mm, observation.pressure_hpa,
              extensions.st_distance(
                observation.location,
                extensions.st_setsrid(
                  extensions.st_makepoint(:longitude, :latitude), 4326
                )::extensions.geography
              ) / 1000.0 as distance_km
            from vigia.weather_observations observation
            where observation.value_type = 'OBSERVADO'
              and observation.observed_at <= :as_of
              and observation.observed_at >= :oldest
              and extensions.st_dwithin(
                observation.location,
                extensions.st_setsrid(
                  extensions.st_makepoint(:longitude, :latitude), 4326
                )::extensions.geography,
                :maximum_distance_m
              )
            order by observation.station_code, observation.observed_at desc
            limit :limit
            """
        )
        return await self._database._mapped_query(  # noqa: SLF001
            statement,
            {
                "longitude": longitude,
                "latitude": latitude,
                "as_of": as_of,
                "oldest": as_of - max_age,
                "maximum_distance_m": max_distance_km * 1000.0,
                "limit": limit,
            },
            "No se pudo consultar la meteorología de riesgo.",
        )

    async def persist_assessment(
        self,
        assessment: RiskAssessment,
        *,
        aoi_geojson: dict[str, Any],
        longitude: float,
        latitude: float,
        configuration: dict[str, Any],
        input_snapshot: dict[str, Any],
        software_version: str,
        code_commit: str,
        request_id: str,
        started_at: datetime,
        finished_at: datetime,
        raster_product_id: UUID | None = None,
    ) -> UUID:
        aoi_hash = canonical_hash(aoi_geojson)
        configuration_hash = canonical_hash(configuration)
        input_snapshot_hash = canonical_hash(input_snapshot)
        component_scores = {item.name: item.score for item in assessment.components}
        component_details = {
            item.name: {
                "source": item.source,
                "observed_at": item.observed_at,
                "resolution_m": item.resolution_m,
                "quality": item.quality,
                "reason_codes": item.reason_codes,
                **item.details,
            }
            for item in assessment.components
        }
        output = {
            "engine_version": assessment.engine_version,
            "mode": assessment.mode,
            "as_of": assessment.as_of,
            "valid_at": assessment.valid_at,
            "experimental_index": assessment.experimental_index,
            "risk_class": assessment.risk_class,
            "data_quality": assessment.data_quality,
            "component_scores": component_scores,
            "reason_codes": assessment.reason_codes,
        }
        output_hash = canonical_hash(output)
        prediction_key = canonical_hash(
            {
                "aoi_hash": aoi_hash,
                "configuration_hash": configuration_hash,
                "input_snapshot_hash": input_snapshot_hash,
                "valid_at": assessment.valid_at,
                "output_hash": output_hash,
            }
        )
        aoi_json = json.dumps(aoi_geojson, separators=(",", ":"))
        async with self._database.transaction() as connection:
            run_row = (
                (
                    await connection.execute(
                        text(
                            """
                        insert into vigia.risk_runs (
                          engine_version, mode, state, as_of, valid_at, horizon_hours,
                          aoi, aoi_hash, configuration, configuration_hash,
                          input_snapshot, input_snapshot_hash, software_version,
                          code_commit, request_id, started_at, finished_at, data_quality
                        ) values (
                          :engine_version, cast(:mode as vigia.risk_mode), 'SUCCEEDED',
                          :as_of, :valid_at, :horizon_hours,
                          extensions.st_multi(extensions.st_setsrid(
                            extensions.st_geomfromgeojson(:aoi), 4326
                          )), :aoi_hash, cast(:configuration as jsonb), :configuration_hash,
                          cast(:input_snapshot as jsonb), :input_snapshot_hash,
                          :software_version, :code_commit, :request_id,
                          :started_at, :finished_at,
                          cast(:data_quality as vigia.risk_data_quality)
                        ) on conflict (
                          engine_version, mode, as_of, valid_at, aoi_hash,
                          configuration_hash, input_snapshot_hash
                        ) do update set finished_at = excluded.finished_at
                        returning id
                        """
                        ),
                        {
                            "engine_version": assessment.engine_version,
                            "mode": assessment.mode,
                            "as_of": assessment.as_of,
                            "valid_at": assessment.valid_at,
                            "horizon_hours": assessment.horizon_hours,
                            "aoi": aoi_json,
                            "aoi_hash": aoi_hash,
                            "configuration": json.dumps(configuration, default=str),
                            "configuration_hash": configuration_hash,
                            "input_snapshot": json.dumps(input_snapshot, default=str),
                            "input_snapshot_hash": input_snapshot_hash,
                            "software_version": software_version,
                            "code_commit": code_commit,
                            "request_id": request_id,
                            "started_at": started_at,
                            "finished_at": finished_at,
                            "data_quality": assessment.data_quality,
                        },
                    )
                )
                .mappings()
                .one()
            )
            prediction_row = (
                (
                    await connection.execute(
                        text(
                            """
                        insert into vigia.risk_predictions (
                          valid_at, geometry, risk_score, level, top_factors, data_quality,
                          run_id, prediction_key, mode, as_of, horizon_hours, centroid,
                          experimental_index, risk_class, component_scores, component_details,
                          reason_codes, explanations, missing_components, input_resolutions,
                          engine_version, configuration_hash, input_snapshot_hash, output_hash,
                          raster_product_id, experimental
                        ) values (
                          :valid_at, extensions.st_setsrid(
                            extensions.st_geomfromgeojson(:aoi), 4326
                          ), null, null, '{}'::jsonb,
                          jsonb_build_object('phase5', cast(:data_quality as text)),
                          :run_id, :prediction_key, cast(:mode as vigia.risk_mode),
                          :as_of, :horizon_hours,
                          extensions.st_setsrid(
                            extensions.st_makepoint(:longitude, :latitude), 4326
                          )::extensions.geography,
                          :experimental_index, :risk_class,
                          cast(:component_scores as jsonb), cast(:component_details as jsonb),
                          :reason_codes, :explanations, :missing_components,
                          cast(:input_resolutions as jsonb), :engine_version,
                          :configuration_hash, :input_snapshot_hash, :output_hash,
                          :raster_product_id, true
                        ) on conflict (prediction_key) where prediction_key is not null
                        do update set created_at = vigia.risk_predictions.created_at
                        returning id
                        """
                        ),
                        {
                            "valid_at": assessment.valid_at,
                            "aoi": aoi_json,
                            "data_quality": assessment.data_quality,
                            "run_id": run_row["id"],
                            "prediction_key": prediction_key,
                            "mode": assessment.mode,
                            "as_of": assessment.as_of,
                            "horizon_hours": assessment.horizon_hours,
                            "longitude": longitude,
                            "latitude": latitude,
                            "experimental_index": assessment.experimental_index,
                            "risk_class": assessment.risk_class,
                            "component_scores": json.dumps(component_scores),
                            "component_details": json.dumps(component_details, default=str),
                            "reason_codes": list(assessment.reason_codes),
                            "explanations": list(assessment.explanations),
                            "missing_components": list(assessment.missing_components),
                            "input_resolutions": json.dumps(
                                {item.name: item.resolution_m for item in assessment.components}
                            ),
                            "engine_version": assessment.engine_version,
                            "configuration_hash": configuration_hash,
                            "input_snapshot_hash": input_snapshot_hash,
                            "output_hash": output_hash,
                            "raster_product_id": raster_product_id,
                        },
                    )
                )
                .mappings()
                .one()
            )
            provenance_id = await connection.scalar(
                text(
                    """
                    select id from vigia.data_provenance
                    where entity_type = 'risk_prediction' and entity_id = :entity_id
                      and output_hash = :output_hash
                    order by created_at limit 1
                    """
                ),
                {"entity_id": prediction_row["id"], "output_hash": output_hash},
            )
            if provenance_id is None:
                provenance_id = await connection.scalar(
                    text(
                        """
                        insert into vigia.data_provenance (
                          entity_type, entity_id, dataset, dataset_version, source_timestamp,
                          transformation, code_commit, parameters, input_hashes, output_hash
                        ) values (
                          'risk_prediction', :entity_id, 'VIGIA environmental context',
                          :engine_version, :source_timestamp, 'risk_baseline_v1', :code_commit,
                          cast(:parameters as jsonb), :input_hashes, :output_hash
                        ) returning id
                        """
                    ),
                    {
                        "entity_id": prediction_row["id"],
                        "engine_version": assessment.engine_version,
                        "source_timestamp": assessment.as_of,
                        "code_commit": code_commit,
                        "parameters": json.dumps(configuration),
                        "input_hashes": [input_snapshot_hash],
                        "output_hash": output_hash,
                    },
                )
            await connection.execute(
                text(
                    """
                    update vigia.risk_predictions set provenance_id = :provenance_id
                    where id = :id
                    """
                ),
                {"provenance_id": provenance_id, "id": prediction_row["id"]},
            )
        return UUID(str(prediction_row["id"]))
