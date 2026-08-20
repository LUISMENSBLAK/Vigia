from __future__ import annotations

from collections.abc import Callable
from typing import Any

from vigia_ai.detection.engine import recommend_state
from vigia_ai.detection.models import IncidentState
from vigia_ai.detection.state_machine import transition_path
from vigia_ai.fusion.config import FusionConfig
from vigia_ai.fusion.engine import fuse_observations
from vigia_ai.fusion.geodesy import geodesic_distance_m

from .clock import ReplayClock
from .context import ReplayDataContext
from .models import (
    ReplayCaseManifest,
    ReplayIncidentSnapshot,
    ReplayRunResult,
    ReplayStepOutput,
    RiskReplaySnapshot,
    canonical_hash,
)

RiskProvider = Callable[[Any, tuple[Any, ...]], RiskReplaySnapshot]
StepCallback = Callable[[ReplayStepOutput], None]


def _unavailable_risk(_: Any, __: tuple[Any, ...]) -> RiskReplaySnapshot:
    return RiskReplaySnapshot(
        availability="UNAVAILABLE",
        risk_class="NO_DISPONIBLE",
        data_quality="INSUFFICIENT_DATA",
        reason_codes=("HISTORICAL_FWI_STATE_UNAVAILABLE",),
    )


class ReplayEngine:
    def __init__(
        self,
        *,
        data_context: ReplayDataContext,
        clock: ReplayClock,
        fusion_config: FusionConfig,
        risk_provider: RiskProvider | None = None,
    ) -> None:
        self._data = data_context
        self._clock = clock
        self._config = fusion_config
        self._risk_provider = risk_provider or _unavailable_risk
        self._incidents: dict[str, ReplayIncidentSnapshot] = {}

    def _associate(self, centroid: tuple[float, float], first_observed: Any) -> str:
        matches = [
            (geodesic_distance_m(existing.centroid, centroid), incident_id)
            for incident_id, existing in self._incidents.items()
            if abs((first_observed - existing.first_observation_at).total_seconds())
            <= self._config.max_age_minutes * 60
        ]
        if matches and min(matches)[0] <= self._config.maximum_association_radius_m:
            return min(matches)[1]
        return f"REPLAY-INC-{canonical_hash({'centroid': centroid, 'first': first_observed})[:16]}"

    def run(
        self,
        manifest: ReplayCaseManifest,
        *,
        code_commit: str,
        completed_steps: tuple[ReplayStepOutput, ...] = (),
        on_step: StepCallback | None = None,
    ) -> ReplayRunResult:
        timeline = self._clock.timeline()
        if timeline[0] != manifest.replay_start.astimezone(timeline[0].tzinfo):
            raise ValueError("El clock no coincide con el manifest")
        if len(completed_steps) > len(timeline):
            raise ValueError("El checkpoint contiene más steps que la ventana")
        for index, step in enumerate(completed_steps):
            if step.step_index != index or step.as_of != timeline[index]:
                raise ValueError("El checkpoint no coincide con la timeline")
        steps = list(completed_steps)
        processed_ids: set[str] = set()
        if completed_steps:
            last = completed_steps[-1]
            self._incidents = {
                incident.replay_incident_id: incident for incident in last.incidents
            }
            processed_ids.update(
                item.observation_id
                for item in self._data.thermal_observations(as_of=last.as_of)
            )
        for step_index, cutoff in enumerate(timeline[len(completed_steps) :], len(completed_steps)):
            self._clock.seek(cutoff)
            visible = self._data.visible_inputs(as_of=cutoff)
            observations = self._data.thermal_observations(as_of=cutoff)
            processed_ids.update(item.observation_id for item in observations)
            summary = fuse_observations(observations, config=self._config, as_of=cutoff)
            current_incidents: list[ReplayIncidentSnapshot] = []
            for candidate in summary.candidates:
                recommendation = recommend_state(candidate, config=self._config, as_of=cutoff)
                incident_id = self._associate(candidate.centroid, candidate.first_observation_at)
                previous = self._incidents.get(incident_id)
                previous_state = (
                    IncidentState(previous.state) if previous else IncidentState.SIN_EVIDENCIA
                )
                path = transition_path(previous_state, recommendation.recommended_state)
                state = path[-1] if path else previous_state
                snapshot = ReplayIncidentSnapshot(
                    replay_incident_id=incident_id,
                    state=state.value,
                    centroid=candidate.centroid,
                    first_observation_at=(
                        min(previous.first_observation_at, candidate.first_observation_at)
                        if previous
                        else candidate.first_observation_at
                    ),
                    last_observation_at=candidate.last_observation_at,
                    observation_count=candidate.confirming_count,
                    source_families=tuple(item.value for item in candidate.source_families),
                    reason_codes=tuple(item.value for item in recommendation.reason_codes),
                )
                self._incidents[incident_id] = snapshot
                current_incidents.append(snapshot)
            risk = self._risk_provider(cutoff, visible)
            step_payload = {
                "step_index": step_index,
                "as_of": cutoff,
                "visible_inputs": [item.input_hash for item in visible],
                "incidents": [item.model_dump(mode="json") for item in current_incidents],
                "risk": risk.model_dump(mode="json"),
            }
            step = ReplayStepOutput(
                step_index=step_index,
                as_of=cutoff,
                visible_input_count=len(visible),
                visible_observation_count=len(observations),
                candidate_count=summary.candidate_count,
                incidents=tuple(
                    sorted(current_incidents, key=lambda item: item.replay_incident_id)
                ),
                risk=risk.model_dump(mode="json"),
                availability=self._data.availability(as_of=cutoff),
                exclusion_counts=self._data.exclusion_counts(as_of=cutoff),
                output_hash=canonical_hash(step_payload),
            )
            steps.append(step)
            if on_step is not None:
                on_step(step)
        configuration_hash = self._config.configuration_hash
        run_hash = canonical_hash(
            {
                "manifest_hash": manifest.manifest_hash,
                "configuration_hash": configuration_hash,
                "code_commit": code_commit,
                "engine_versions": {
                    "replay": "replay-v1",
                    "fusion": self._config.version,
                    "detection": self._config.rule_version,
                },
            }
        )
        return ReplayRunResult(
            run_hash=run_hash,
            case_id=manifest.case_id,
            manifest_hash=manifest.manifest_hash,
            configuration_hash=configuration_hash,
            code_commit=code_commit,
            steps=tuple(steps),
            observations_processed=len(processed_ids),
        )
