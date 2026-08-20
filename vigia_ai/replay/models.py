from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

TRUTH_KEYS = {
    "burned_area",
    "final_perimeter",
    "official_area_ha",
    "official_final_state",
    "official_start",
    "perimeter",
    "reference_event",
    "reference_perimeter",
}


def _contains_truth(value: object) -> bool:
    if isinstance(value, dict):
        return bool(TRUTH_KEYS.intersection(value)) or any(
            _contains_truth(item) for item in value.values()
        )
    if isinstance(value, list | tuple):
        return any(_contains_truth(item) for item in value)
    return False


def canonical_hash(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


class ReplayInputKind(StrEnum):
    THERMAL_OBSERVATION = "THERMAL_OBSERVATION"
    WEATHER_OBSERVATION = "WEATHER_OBSERVATION"
    SENTINEL_PRODUCT = "SENTINEL_PRODUCT"
    TERRAIN_PRODUCT = "TERRAIN_PRODUCT"
    LAND_COVER_PRODUCT = "LAND_COVER_PRODUCT"


class ReplayInput(BaseModel):
    input_id: str
    kind: ReplayInputKind
    source: str
    observed_at: datetime
    available_at: datetime
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    payload: dict[str, Any]
    provenance: dict[str, Any]
    availability_basis: Literal[
        "OBSERVED", "PUBLISHED", "RECEIVED", "OBSERVATION_TIME_PROXY"
    ]
    quality_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def temporal_and_spatial_contract(self) -> ReplayInput:
        if self.observed_at.tzinfo is None or self.available_at.tzinfo is None:
            raise ValueError("Los inputs replay requieren zona horaria")
        if self.available_at < self.observed_at:
            raise ValueError("available_at no puede preceder observed_at")
        if (self.longitude is None) != (self.latitude is None):
            raise ValueError("Las coordenadas deben aparecer juntas")
        if self.kind is ReplayInputKind.THERMAL_OBSERVATION and self.longitude is None:
            raise ValueError("Una observación térmica requiere coordenadas")
        if _contains_truth(self.payload):
            raise ValueError("TRUTH_FIREWALL: ground truth no puede entrar en ReplayInput")
        return self

    @property
    def input_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class ReplayCaseManifest(BaseModel):
    case_id: str
    historical_fire_event_id: str | None = None
    case_kind: Literal["POSITIVE_REFERENCE", "CONTROL_NO_KNOWN_FIRE"]
    aoi_geojson: dict[str, Any]
    replay_start: datetime
    replay_end: datetime
    time_step_minutes: int = Field(gt=0, le=1440)
    available_sources: tuple[str, ...]
    reference_sources: tuple[str, ...]
    sensor_availability: dict[str, str]
    input_hashes: tuple[str, ...]
    case_version: str
    selection_policy_version: str
    reference_quality: str

    @model_validator(mode="after")
    def time_order(self) -> ReplayCaseManifest:
        if self.replay_start.tzinfo is None or self.replay_end.tzinfo is None:
            raise ValueError("La ventana de replay requiere zona horaria")
        if self.replay_end <= self.replay_start:
            raise ValueError("replay_end debe ser posterior a replay_start")
        if self.case_kind == "POSITIVE_REFERENCE" and self.historical_fire_event_id is None:
            raise ValueError("Un caso positivo requiere referencia histórica")
        self.available_sources = tuple(sorted(set(self.available_sources)))
        self.reference_sources = tuple(sorted(set(self.reference_sources)))
        self.input_hashes = tuple(sorted(set(self.input_hashes)))
        return self

    @property
    def manifest_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class ExclusionExplanation(BaseModel):
    input_id: str
    included: bool
    reason: str
    observed_at: datetime
    available_at: datetime


class ReplayIncidentSnapshot(BaseModel):
    replay_incident_id: str
    state: str
    centroid: tuple[float, float]
    first_observation_at: datetime
    last_observation_at: datetime
    observation_count: int = Field(ge=1)
    source_families: tuple[str, ...]
    reason_codes: tuple[str, ...]


class ReplayStepOutput(BaseModel):
    step_index: int = Field(ge=0)
    as_of: datetime
    visible_input_count: int = Field(ge=0)
    visible_observation_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    incidents: tuple[ReplayIncidentSnapshot, ...]
    risk: dict[str, Any]
    availability: dict[str, str]
    exclusion_counts: dict[str, int]
    output_hash: str


class ReplayRunResult(BaseModel):
    run_hash: str
    case_id: str
    manifest_hash: str
    configuration_hash: str
    code_commit: str
    steps: tuple[ReplayStepOutput, ...]
    observations_processed: int = Field(ge=0)
    deterministic: bool = True
    live_state_mutated: Literal[False] = False


class RiskReplaySnapshot(BaseModel):
    availability: str
    experimental_index: float | None = Field(default=None, ge=0, le=100)
    risk_class: str
    data_quality: str
    reason_codes: tuple[str, ...] = ()
