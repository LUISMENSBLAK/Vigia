from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text

from services.api.vigia_api.database import VigiaDatabase

from .models import ReplayCaseManifest, ReplayInput, ReplayRunResult, canonical_hash


class ReplayRepository:
    def __init__(self, database: VigiaDatabase) -> None:
        self._database = database

    async def persist_case(
        self, manifest: ReplayCaseManifest, inputs: tuple[ReplayInput, ...]
    ) -> UUID:
        aoi_json = json.dumps(manifest.aoi_geojson, separators=(",", ":"))
        async with self._database.transaction() as connection:
            historical_fire_id = None
            if manifest.historical_fire_event_id is not None:
                historical_fire_id = await connection.scalar(
                    text("select id from vigia.historical_fires where event_key = :event_key"),
                    {"event_key": manifest.historical_fire_event_id},
                )
                if historical_fire_id is None:
                    raise RuntimeError("La referencia histórica del caso no existe")
            case_id = await connection.scalar(
                text(
                    """
                    insert into vigia.replay_cases (
                      case_key, historical_fire_id, kind, aoi, replay_start, replay_end,
                      time_step_minutes, manifest, manifest_hash, case_version,
                      selection_policy_version, available_sources, reference_sources,
                      sensor_availability, reference_quality, frozen
                    ) values (
                      :case_key, :historical_fire_id,
                      cast(:kind as vigia.replay_case_kind),
                      extensions.st_multi(extensions.st_setsrid(
                        extensions.st_geomfromgeojson(:aoi), 4326
                      )), :replay_start, :replay_end, :time_step_minutes,
                      cast(:manifest as jsonb), :manifest_hash, :case_version,
                      :selection_policy_version, :available_sources, :reference_sources,
                      cast(:sensor_availability as jsonb),
                      cast(:reference_quality as vigia.reference_quality), true
                    ) on conflict (case_key) do update set
                      frozen = true,
                      updated_at = now()
                    where vigia.replay_cases.manifest_hash = excluded.manifest_hash
                    returning id
                    """
                ),
                {
                    "case_key": manifest.case_id,
                    "historical_fire_id": historical_fire_id,
                    "kind": manifest.case_kind,
                    "aoi": aoi_json,
                    "replay_start": manifest.replay_start,
                    "replay_end": manifest.replay_end,
                    "time_step_minutes": manifest.time_step_minutes,
                    "manifest": manifest.model_dump_json(),
                    "manifest_hash": manifest.manifest_hash,
                    "case_version": manifest.case_version,
                    "selection_policy_version": manifest.selection_policy_version,
                    "available_sources": list(manifest.available_sources),
                    "reference_sources": list(manifest.reference_sources),
                    "sensor_availability": json.dumps(manifest.sensor_availability),
                    "reference_quality": manifest.reference_quality,
                },
            )
            if not isinstance(case_id, UUID):
                raise RuntimeError("ReplayCase congelado: el manifest no puede cambiar")
            for item in inputs:
                input_id = await connection.scalar(
                    text(
                        """
                        insert into vigia.replay_inputs (
                          case_id, input_key, kind, source_code, observed_at, available_at,
                          location, payload, provenance, availability_basis,
                          quality_flags, input_hash
                        ) values (
                          :case_id, :input_key, cast(:kind as vigia.replay_input_kind),
                          :source_code, :observed_at, :available_at,
                          case when cast(:longitude as double precision) is null
                            then null else
                            extensions.st_setsrid(
                              extensions.st_makepoint(
                                cast(:longitude as double precision),
                                cast(:latitude as double precision)
                              ), 4326
                            )::extensions.geography end,
                          cast(:payload as jsonb), cast(:provenance as jsonb),
                          :availability_basis, :quality_flags, :input_hash
                        ) on conflict (case_id, input_key) do update set
                          input_key = excluded.input_key
                        where vigia.replay_inputs.input_hash = excluded.input_hash
                        returning id
                        """
                    ),
                    {
                        "case_id": case_id,
                        "input_key": item.input_id,
                        "kind": item.kind.value,
                        "source_code": item.source,
                        "observed_at": item.observed_at,
                        "available_at": item.available_at,
                        "longitude": item.longitude,
                        "latitude": item.latitude,
                        "payload": json.dumps(item.payload),
                        "provenance": json.dumps(item.provenance, default=str),
                        "availability_basis": item.availability_basis,
                        "quality_flags": list(item.quality_flags),
                        "input_hash": item.input_hash,
                    },
                )
                if not isinstance(input_id, UUID):
                    raise RuntimeError("ReplayInput congelado: el contenido no puede cambiar")
        return case_id

    async def persist_run(
        self,
        result: ReplayRunResult,
        *,
        configuration: dict[str, object],
        started_at: datetime,
        elapsed_ms: int,
        approximate_peak_memory_bytes: int | None,
    ) -> UUID:
        input_snapshot_hash = canonical_hash(
            {"case": result.case_id, "manifest": result.manifest_hash}
        )
        async with self._database.transaction() as connection:
            case_id = await connection.scalar(
                text("select id from vigia.replay_cases where case_key = :case_key"),
                {"case_key": result.case_id},
            )
            if case_id is None:
                raise RuntimeError("ReplayCase no persistido")
            run_id = await connection.scalar(
                text(
                    """
                    insert into vigia.replay_runs (
                      case_id, run_hash, state, code_commit, engine_versions,
                      configuration, configuration_hash, case_manifest_hash,
                      input_snapshot_hash, started_at, completed_at, step_count,
                      completed_step, observations_processed, wall_time_ms,
                      approximate_peak_memory_bytes, deterministic, live_state_mutated
                    ) values (
                      :case_id, :run_hash, 'SUCCEEDED', :code_commit,
                      cast(:engine_versions as jsonb), cast(:configuration as jsonb),
                      :configuration_hash, :manifest_hash, :input_snapshot_hash,
                      :started_at, :completed_at, :step_count, :completed_step,
                      :observations_processed, :wall_time_ms, :peak_memory,
                      :deterministic, false
                    ) on conflict (run_hash) do update set
                      run_hash = vigia.replay_runs.run_hash
                    returning id
                    """
                ),
                {
                    "case_id": case_id,
                    "run_hash": result.run_hash,
                    "code_commit": result.code_commit,
                    "engine_versions": json.dumps(
                        {"replay": "replay-v1", "fusion_detection": "baseline-v1"}
                    ),
                    "configuration": json.dumps(configuration),
                    "configuration_hash": result.configuration_hash,
                    "manifest_hash": result.manifest_hash,
                    "input_snapshot_hash": input_snapshot_hash,
                    "started_at": started_at,
                    "completed_at": datetime.now(UTC),
                    "step_count": len(result.steps),
                    "completed_step": len(result.steps) - 1,
                    "observations_processed": result.observations_processed,
                    "wall_time_ms": elapsed_ms,
                    "peak_memory": approximate_peak_memory_bytes,
                    "deterministic": result.deterministic,
                },
            )
            if not isinstance(run_id, UUID):
                raise RuntimeError("No se pudo persistir ReplayRun")
            for step in result.steps:
                step_id = await connection.scalar(
                    text(
                        """
                        insert into vigia.replay_steps (
                          replay_run_id, step_index, as_of, visible_input_count,
                          visible_observation_count, candidate_count, incidents, risk,
                          availability, exclusion_counts, output_hash
                        ) values (
                          :run_id, :step_index, :as_of, :visible_input_count,
                          :visible_observation_count, :candidate_count,
                          cast(:incidents as jsonb), cast(:risk as jsonb),
                          cast(:availability as jsonb), cast(:exclusion_counts as jsonb),
                          :output_hash
                        ) on conflict (replay_run_id, step_index) do update set
                          output_hash = vigia.replay_steps.output_hash
                        where vigia.replay_steps.output_hash = excluded.output_hash
                        returning id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "step_index": step.step_index,
                        "as_of": step.as_of,
                        "visible_input_count": step.visible_input_count,
                        "visible_observation_count": step.visible_observation_count,
                        "candidate_count": step.candidate_count,
                        "incidents": json.dumps(
                            [item.model_dump(mode="json") for item in step.incidents]
                        ),
                        "risk": json.dumps(step.risk),
                        "availability": json.dumps(step.availability),
                        "exclusion_counts": json.dumps(step.exclusion_counts),
                        "output_hash": step.output_hash,
                    },
                )
                if not isinstance(step_id, UUID):
                    raise RuntimeError("Replay no determinista: cambió un step existente")
        return run_id
