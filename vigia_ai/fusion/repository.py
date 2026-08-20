import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text

from services.api.vigia_api.database import VigiaDatabase
from vigia_ai.detection.models import DetectionRecommendation, IncidentState
from vigia_ai.detection.state_machine import transition_path

from .config import FusionConfig
from .models import FusionRunSummary, IncidentCandidate, ObservationEvidence
from .normalization import normalize_database_row

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class FusionRun:
    id: UUID
    started_at: datetime
    request_id: str
    as_of: datetime


@dataclass(frozen=True, slots=True)
class PersistedFusionResult:
    incidents_created: int
    incidents_updated: int
    incidents_unchanged: int


class FusionRepository:
    def __init__(self, database: VigiaDatabase) -> None:
        self._database = database

    async def load_observations(
        self,
        *,
        config: FusionConfig,
        observed_from: datetime,
        observed_to: datetime,
        as_of: datetime,
        limit: int = 50_000,
    ) -> list[ObservationEvidence]:
        if observed_to < observed_from or as_of.tzinfo is None:
            raise ValueError("La ventana de observaciones no es válida.")
        statement = text(
            """
            with normalized_observations as (
            select
              o.id, s.code as source_code, s.name as source_name, s.provider,
              o.platform, o.sensor, o.observed_at, o.received_at,
              extensions.st_x(o.location::extensions.geometry) as longitude,
              extensions.st_y(o.location::extensions.geometry) as latitude,
              o.confidence_raw, o.fire_probability, o.frp_mw, o.brightness_kelvin,
              o.daynight, o.quality,
              case when p.id is null then null else jsonb_build_object(
                'dataset', p.dataset, 'dataset_version', p.dataset_version,
                'source_timestamp', p.source_timestamp, 'transformation', p.transformation,
                'code_commit', p.code_commit, 'input_hashes', p.input_hashes,
                'output_hash', p.output_hash
              ) end as provenance,
              exists (
                select 1 from vigia.known_heat_sources heat
                where extensions.st_dwithin(o.location, heat.location, heat.match_radius_m)
                  and heat.created_at <= :as_of
                  and (heat.valid_from is null or heat.valid_from <= o.observed_at)
                  and (heat.valid_to is null or heat.valid_to >= o.observed_at)
              ) as known_heat_source_match
            from vigia.fire_observations o
            join vigia.sources s on s.id = o.source_id
            left join lateral (
              select provenance.* from vigia.data_provenance provenance
              where provenance.entity_type = 'fire_observation'
                and provenance.entity_id = o.id
                and provenance.created_at <= :as_of
              order by provenance.created_at desc limit 1
            ) p on true
            where o.observed_at between :observed_from and :observed_to
              and o.observed_at <= :as_of
              and o.received_at <= :as_of
            union all
            select
              weather.id, s.code, s.name, s.provider,
              'GROUND_STATION' as platform, weather.station_code as sensor,
              weather.observed_at, weather.received_at,
              extensions.st_x(weather.location::extensions.geometry) as longitude,
              extensions.st_y(weather.location::extensions.geometry) as latitude,
              null::text as confidence_raw, null::double precision as fire_probability,
              null::double precision as frp_mw, null::double precision as brightness_kelvin,
              null::text as daynight, weather.quality,
              case when weather_provenance.id is null then null else jsonb_build_object(
                'dataset', weather_provenance.dataset,
                'dataset_version', weather_provenance.dataset_version,
                'source_timestamp', weather_provenance.source_timestamp,
                'transformation', weather_provenance.transformation,
                'code_commit', weather_provenance.code_commit,
                'input_hashes', weather_provenance.input_hashes,
                'output_hash', weather_provenance.output_hash
              ) end as provenance,
              false as known_heat_source_match
            from vigia.weather_observations weather
            join vigia.sources s on s.id = weather.source_id
            left join lateral (
              select provenance.* from vigia.data_provenance provenance
              where provenance.entity_type = 'weather_observation'
                and provenance.entity_id = weather.id
                and provenance.created_at <= :as_of
              order by provenance.created_at desc limit 1
            ) weather_provenance on true
            where weather.observed_at between :observed_from and :observed_to
              and weather.observed_at <= :as_of
              and weather.received_at <= :as_of
            )
            select * from normalized_observations
            order by observed_at, id
            limit :limit
            """
        )
        async with self._database.transaction() as connection:
            rows = (
                await connection.execute(
                    statement,
                    {
                        "observed_from": observed_from,
                        "observed_to": observed_to,
                        "as_of": as_of,
                        "limit": limit,
                    },
                )
            ).mappings().all()
        return [
            normalize_database_row(dict(row), config=config, as_of=as_of) for row in rows
        ]

    async def begin_run(
        self,
        *,
        started_at: datetime,
        as_of: datetime,
        observed_from: datetime,
        observed_to: datetime,
        software_version: str,
        code_commit: str,
        request_id: str,
        config: FusionConfig,
    ) -> FusionRun:
        statement = text(
            """
            insert into vigia.fusion_runs (
              started_at, as_of, observation_from, observation_to, software_version,
              code_commit, request_id, configuration, configuration_hash, state
            ) values (
              :started_at, :as_of, :observed_from, :observed_to, :software_version,
              :code_commit, :request_id, cast(:configuration as jsonb),
              :configuration_hash, 'RUNNING'
            ) returning id, started_at, request_id, as_of
            """
        )
        async with self._database.transaction() as connection:
            row = (
                await connection.execute(
                    statement,
                    {
                        "started_at": started_at,
                        "as_of": as_of,
                        "observed_from": observed_from,
                        "observed_to": observed_to,
                        "software_version": software_version,
                        "code_commit": code_commit,
                        "request_id": request_id,
                        "configuration": config.canonical_json(),
                        "configuration_hash": config.configuration_hash,
                    },
                )
            ).mappings().one()
        return FusionRun(
            id=row["id"],
            started_at=row["started_at"],
            request_id=row["request_id"],
            as_of=row["as_of"],
        )

    async def persist(
        self,
        run: FusionRun,
        summary: FusionRunSummary,
        recommendations: dict[str, DetectionRecommendation],
        *,
        config: FusionConfig,
        code_commit: str,
        software_version: str,
        completed_at: datetime,
    ) -> PersistedFusionResult:
        created = 0
        updated = 0
        unchanged = 0
        source_set: set[str] = set()
        async with self._database.transaction() as connection:
            for candidate in summary.candidates:
                recommendation = recommendations[candidate.candidate_id]
                source_set.update(family.value for family in candidate.source_families)
                candidate_row = (
                    await connection.execute(
                        text(
                            """
                            insert into vigia.incident_candidates (
                              fusion_run_id, candidate_key, first_observation_at,
                              last_observation_at, centroid, spatial_extent_m,
                              observation_count, platforms, sensors, source_families,
                              persistence, data_quality, recommendation, evidence_strength,
                              reason_codes, explanation, configuration_hash
                            ) values (
                              :fusion_run_id, :candidate_key, :first_observation_at,
                              :last_observation_at,
                              extensions.st_setsrid(
                                extensions.st_makepoint(:longitude, :latitude), 4326
                              )::extensions.geography,
                              :spatial_extent_m, :observation_count, :platforms, :sensors,
                              :source_families, cast(:persistence as jsonb),
                              cast(:data_quality as vigia.data_quality_state),
                              cast(:recommendation as vigia.incident_state),
                              cast(:evidence_strength as vigia.evidence_strength),
                              :reason_codes, cast(:explanation as jsonb), :configuration_hash
                            ) returning id
                            """
                        ),
                        self._candidate_parameters(run.id, candidate, recommendation),
                    )
                ).mappings().one()
                if candidate.confirming_count < config.incident_min_observations:
                    continue
                incident_action = await self._persist_incident(
                    connection,
                    run=run,
                    candidate_id=candidate_row["id"],
                    candidate=candidate,
                    recommendation=recommendation,
                    code_commit=code_commit,
                    software_version=software_version,
                    completed_at=completed_at,
                )
                created += incident_action == "created"
                updated += incident_action == "updated"
                unchanged += incident_action == "unchanged"

            await connection.execute(
                text(
                    """
                    update vigia.fusion_runs set
                      completed_at = :completed_at, state = 'SUCCEEDED',
                      source_set = :source_set,
                      observations_received = :observations_received,
                      observations_eligible = :observations_eligible,
                      candidates_found = :candidates_found,
                      incidents_created = :incidents_created,
                      incidents_updated = :incidents_updated
                    where id = :run_id
                    """
                ),
                {
                    "completed_at": completed_at,
                    "source_set": sorted(source_set),
                    "observations_received": summary.input_observation_count,
                    "observations_eligible": summary.eligible_observation_count,
                    "candidates_found": summary.candidate_count,
                    "incidents_created": created,
                    "incidents_updated": updated,
                    "run_id": run.id,
                },
            )
        return PersistedFusionResult(created, updated, unchanged)

    async def fail_run(
        self, run: FusionRun, *, error_code: str, completed_at: datetime
    ) -> None:
        async with self._database.transaction() as connection:
            await connection.execute(
                text(
                    """
                    update vigia.fusion_runs set
                      completed_at = :completed_at,
                      state = 'FAILED',
                      errors = cast(:errors as jsonb)
                    where id = :run_id
                    """
                ),
                {
                    "completed_at": completed_at,
                    "errors": json.dumps([{"code": error_code}]),
                    "run_id": run.id,
                },
            )

    @staticmethod
    def _candidate_parameters(
        run_id: UUID,
        candidate: IncidentCandidate,
        recommendation: DetectionRecommendation,
    ) -> dict[str, Any]:
        longitude, latitude = candidate.centroid
        return {
            "fusion_run_id": run_id,
            "candidate_key": candidate.candidate_id,
            "first_observation_at": candidate.first_observation_at,
            "last_observation_at": candidate.last_observation_at,
            "longitude": longitude,
            "latitude": latitude,
            "spatial_extent_m": candidate.spatial_extent_m,
            "observation_count": candidate.confirming_count,
            "platforms": list(candidate.platforms),
            "sensors": list(candidate.sensors),
            "source_families": [family.value for family in candidate.source_families],
            "persistence": candidate.persistence.model_dump_json(),
            "data_quality": candidate.data_quality.value,
            "recommendation": recommendation.recommended_state.value,
            "evidence_strength": recommendation.evidence_strength.value,
            "reason_codes": [code.value for code in recommendation.reason_codes],
            "explanation": json.dumps(
                {
                    "why": recommendation.explanations,
                    "missing_information": recommendation.missing_information,
                },
                ensure_ascii=True,
            ),
            "configuration_hash": candidate.configuration_hash,
        }

    async def _persist_incident(
        self,
        connection: Any,
        *,
        run: FusionRun,
        candidate_id: UUID,
        candidate: IncidentCandidate,
        recommendation: DetectionRecommendation,
        code_commit: str,
        software_version: str,
        completed_at: datetime,
    ) -> str:
        code = incident_code(candidate)
        existing = (
            await connection.execute(
                text(
                    """
                    select id, state::text, last_observation_at, observation_count,
                      configuration_hash, rule_version, last_fusion_as_of
                    from vigia.fire_incidents where code = :code
                    """
                ),
                {"code": code},
            )
        ).mappings().one_or_none()
        initial_state = (
            IncidentState(existing["state"])
            if existing
            else IncidentState.SIN_EVIDENCIA
        )
        historical_replay = bool(
            existing
            and existing["last_fusion_as_of"] is not None
            and run.as_of < existing["last_fusion_as_of"]
        )
        path = (
            ()
            if historical_replay
            else transition_path(initial_state, recommendation.recommended_state)
        )
        stored_state = path[-1] if path else initial_state
        longitude, latitude = candidate.centroid
        incident = (
            await connection.execute(
                text(
                    """
                    with upserted as (
                    insert into vigia.fire_incidents (
                      code, state, centroid, first_signal_at, last_observation_at,
                      public_visible, observation_count, source_families, evidence_strength,
                      reason_codes, explanation, persistence, fusion_data_quality, processed_at,
                      last_fusion_as_of, configuration_hash, rule_version, stale,
                      inactive_at, updated_at
                    ) values (
                      :code, cast(:state as vigia.incident_state),
                      extensions.st_setsrid(
                        extensions.st_makepoint(:longitude, :latitude), 4326
                      )::extensions.geography,
                      :first_signal_at, :last_observation_at, true, :observation_count,
                      :source_families, cast(:evidence_strength as vigia.evidence_strength),
                      :reason_codes, cast(:explanation as jsonb), cast(:persistence as jsonb),
                      cast(:data_quality as vigia.data_quality_state), :processed_at, :as_of,
                      :configuration_hash, :rule_version, :stale, :inactive_at, :updated_at
                    ) on conflict (code) do update set
                      state = excluded.state,
                      centroid = excluded.centroid,
                      first_signal_at = least(
                        vigia.fire_incidents.first_signal_at, excluded.first_signal_at
                      ),
                      last_observation_at = greatest(
                        vigia.fire_incidents.last_observation_at, excluded.last_observation_at
                      ),
                      observation_count = excluded.observation_count,
                      source_families = excluded.source_families,
                      evidence_strength = excluded.evidence_strength,
                      reason_codes = excluded.reason_codes,
                      explanation = excluded.explanation,
                      persistence = excluded.persistence,
                      fusion_data_quality = excluded.fusion_data_quality,
                      processed_at = excluded.processed_at,
                      last_fusion_as_of = excluded.last_fusion_as_of,
                      configuration_hash = excluded.configuration_hash,
                      rule_version = excluded.rule_version,
                      stale = excluded.stale,
                      inactive_at = excluded.inactive_at,
                      updated_at = excluded.updated_at
                    where vigia.fire_incidents.last_fusion_as_of is null
                      or excluded.last_fusion_as_of >= vigia.fire_incidents.last_fusion_as_of
                    returning id
                    )
                    select id from upserted
                    union all
                    select id from vigia.fire_incidents where code = :code
                    limit 1
                    """
                ),
                {
                    **self._candidate_parameters(run.id, candidate, recommendation),
                    "code": code,
                    "state": stored_state.value,
                    "first_signal_at": candidate.first_observation_at,
                    "last_observation_at": candidate.last_observation_at,
                    "processed_at": completed_at,
                    "as_of": run.as_of,
                    "rule_version": recommendation.rule_version,
                    "stale": "STALE_DATA" in {
                        code.value for code in recommendation.reason_codes
                    },
                    "inactive_at": (
                        completed_at
                        if any(
                            code.value == "STALE_DATA"
                            for code in recommendation.reason_codes
                        )
                        else None
                    ),
                    "updated_at": completed_at,
                },
            )
        ).mappings().one()
        incident_id = incident["id"]
        for item in candidate.observations:
            if item.observation.source_family.value == "AEMET_WEATHER":
                await connection.execute(
                    text(
                        """
                        insert into vigia.incident_context_evidence (
                          incident_id, entity_type, entity_id, evidence_role,
                          reason_codes, rule_version
                        ) values (
                          :incident_id, 'weather_observation', cast(:entity_id as uuid),
                          :evidence_role, :reason_codes, :rule_version
                        ) on conflict (incident_id, entity_type, entity_id) do update set
                          evidence_role = excluded.evidence_role,
                          reason_codes = excluded.reason_codes,
                          rule_version = excluded.rule_version
                        """
                    ),
                    {
                        "incident_id": incident_id,
                        "entity_id": item.observation.observation_id,
                        "evidence_role": item.role.value,
                        "reason_codes": list(item.reason_codes),
                        "rule_version": recommendation.rule_version,
                    },
                )
                continue
            if item.observation.source_family.value in {"TERRAIN", "VEGETATION"}:
                continue
            await connection.execute(
                text(
                    """
                    insert into vigia.observation_evidence (
                      incident_id, observation_id, evidence_role, weight_model_version
                    ) values (
                      :incident_id, :observation_id, :evidence_role, :rule_version
                    ) on conflict (incident_id, observation_id) do update set
                      evidence_role = excluded.evidence_role,
                      weight_model_version = excluded.weight_model_version
                    """
                ),
                {
                    "incident_id": incident_id,
                    "observation_id": item.observation.observation_id,
                    "evidence_role": item.role.value,
                    "rule_version": recommendation.rule_version,
                },
            )
        previous = initial_state
        for new_state in path:
            await connection.execute(
                text(
                    """
                    insert into vigia.incident_status_history (
                      incident_id, previous_state, state, changed_at, changed_by,
                      reason, evidence_snapshot, model_version, commit_sha,
                      configuration_hash, software_version, rule_version, fusion_run_id
                    ) values (
                      :incident_id, cast(:previous_state as vigia.incident_state),
                      cast(:state as vigia.incident_state), :changed_at, 'fusion_engine',
                      :reason, cast(:evidence_snapshot as jsonb), null, :commit_sha,
                      :configuration_hash, :software_version, :rule_version, :fusion_run_id
                    )
                    """
                ),
                {
                    "incident_id": incident_id,
                    "previous_state": previous.value,
                    "state": new_state.value,
                    "changed_at": completed_at,
                    "reason": ",".join(code.value for code in recommendation.reason_codes),
                    "evidence_snapshot": json.dumps(
                        {
                            "candidate_id": candidate.candidate_id,
                            "observation_ids": [
                                item.observation.observation_id
                                for item in candidate.observations
                            ],
                        },
                        ensure_ascii=True,
                    ),
                    "commit_sha": code_commit,
                    "configuration_hash": candidate.configuration_hash,
                    "software_version": software_version,
                    "rule_version": recommendation.rule_version,
                    "fusion_run_id": run.id,
                },
            )
            previous = new_state
        evidence_changed = existing is not None and not historical_replay and (
            existing["last_observation_at"] != candidate.last_observation_at
            or existing["observation_count"] != candidate.confirming_count
            or existing["configuration_hash"] != candidate.configuration_hash
            or existing["rule_version"] != recommendation.rule_version
        )
        action = (
            "created"
            if existing is None
            else "updated"
            if path or evidence_changed
            else "unchanged"
        )
        await connection.execute(
            text(
                """
                insert into vigia.fusion_run_incidents (
                  fusion_run_id, incident_id, candidate_id, action
                ) values (:fusion_run_id, :incident_id, :candidate_id, :action)
                on conflict (fusion_run_id, incident_id) do nothing
                """
            ),
            {
                "fusion_run_id": run.id,
                "incident_id": incident_id,
                "candidate_id": candidate_id,
                "action": action,
            },
        )
        logger.info(
            "fusion_incident_persisted",
            fusion_run_id=str(run.id),
            request_id=run.request_id,
            incident_id=str(incident_id),
            action=action,
        )
        return action


def incident_code(candidate: IncidentCandidate) -> str:
    confirming = sorted(
        (
            item.observation.observed_at.isoformat(),
            item.observation.observation_id,
        )
        for item in candidate.observations
        if item.role.value == "confirming"
    )
    if not confirming:
        raise ValueError("Un incidente requiere al menos una observación confirmatoria.")
    incident_identity = json.dumps(confirming[0], ensure_ascii=True, separators=(",", ":"))
    incident_key = hashlib.sha256(incident_identity.encode()).hexdigest()
    return f"VIGIA-{incident_key[:16].upper()}"
