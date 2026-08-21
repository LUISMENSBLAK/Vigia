from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vigia_ai.replay.models import canonical_hash


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class SplitRole(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


class ValidationCaseKind(StrEnum):
    POSITIVE_REFERENCE = "POSITIVE_REFERENCE"
    NO_KNOWN_FIRE_CONTROL = "NO_KNOWN_FIRE_CONTROL"
    HARD_NEGATIVE = "HARD_NEGATIVE"


class MetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    NO_DISPONIBLE = "NO_DISPONIBLE"


class EligibilityReason(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INSUFFICIENT_TEMPORAL_PRECISION = "INSUFFICIENT_TEMPORAL_PRECISION"
    INSUFFICIENT_SPATIAL_PRECISION = "INSUFFICIENT_SPATIAL_PRECISION"
    NO_SENSOR_COVERAGE = "NO_SENSOR_COVERAGE"
    NO_REFERENCE_PERIMETER = "NO_REFERENCE_PERIMETER"
    NO_CONTROL_COVERAGE = "NO_CONTROL_COVERAGE"
    OPERATIONAL_AVAILABILITY_UNKNOWN = "OPERATIONAL_AVAILABILITY_UNKNOWN"
    NO_REPLAY_OUTPUT = "NO_REPLAY_OUTPUT"
    NO_RISK_VALUE = "NO_RISK_VALUE"


class ErrorReason(StrEnum):
    MISSED_NO_SENSOR_SIGNAL = "MISSED_NO_SENSOR_SIGNAL"
    MISSED_CLUSTERING = "MISSED_CLUSTERING"
    MISSED_STATE_THRESHOLD = "MISSED_STATE_THRESHOLD"
    FALSE_SINGLE_PASS = "FALSE_SINGLE_PASS"  # noqa: S105 - scientific reason code
    FALSE_RECURRENT_HEAT_SOURCE = "FALSE_RECURRENT_HEAT_SOURCE"
    FALSE_SPATIAL_MERGE = "FALSE_SPATIAL_MERGE"
    FALSE_TEMPORAL_MERGE = "FALSE_TEMPORAL_MERGE"
    REFERENCE_UNCERTAIN = "REFERENCE_UNCERTAIN"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class SourceSnapshot(FrozenModel):
    source: str
    dataset: str
    source_uri: str
    checksum_sha256: str = Field(min_length=64, max_length=64)
    retrieved_at: datetime
    raw_record_count: int = Field(ge=0)
    normalized_event_count: int = Field(ge=0)
    years_covered: tuple[int, ...]
    regions_covered: tuple[str, ...]
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def timezone_required(self) -> SourceSnapshot:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at requiere zona horaria")
        return self


class ValidationEvent(FrozenModel):
    event_id: str
    event_group_id: str
    kind: Literal[ValidationCaseKind.POSITIVE_REFERENCE]
    region: str
    provinces: tuple[str, ...]
    reference_time: datetime
    temporal_precision: Literal["MINUTE", "EXACT"]
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    spatial_precision: Literal["APPROXIMATE_POINT", "INITIAL_POINT", "PERIMETER"]
    reference_quality: Literal["HIGH"]
    reference_sources: tuple[str, ...]
    reference_hash: str = Field(min_length=64, max_length=64)
    area_ha: float | None = Field(default=None, ge=0)
    has_reference_perimeter: bool = False
    sensor_coverage: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def temporal_contract(self) -> ValidationEvent:
        if self.reference_time.tzinfo is None:
            raise ValueError("reference_time requiere zona horaria")
        return self


class ControlWindow(FrozenModel):
    control_id: str
    event_group_id: str
    kind: Literal[
        ValidationCaseKind.NO_KNOWN_FIRE_CONTROL,
        ValidationCaseKind.HARD_NEGATIVE,
    ]
    region: str
    start: datetime
    end: datetime
    aoi_hash: str = Field(min_length=64, max_length=64)
    area_km2: float = Field(gt=0)
    selection_method: str
    exclusion_checks: tuple[str, ...]
    sensor_coverage: dict[str, str]
    reference_sources: tuple[str, ...]
    quality: Literal["HIGH", "MEDIUM", "LOW"]
    evidence_hash: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def control_contract(self) -> ControlWindow:
        if self.start.tzinfo is None or self.end.tzinfo is None or self.end <= self.start:
            raise ValueError("La ventana de control requiere un intervalo zonificado válido")
        if not self.selection_method or not self.exclusion_checks or not self.reference_sources:
            raise ValueError("Un control necesita método, exclusiones y fuentes verificables")
        return self


class HistoricalCorpusVersion(FrozenModel):
    dataset_version: str
    created_at: datetime
    sources: tuple[SourceSnapshot, ...]
    events: tuple[ValidationEvent, ...]
    controls: tuple[ControlWindow, ...]
    filters: dict[str, Any]
    selection_policy_version: str
    regions_covered: tuple[str, ...]
    years_covered: tuple[int, ...]
    events_per_region: dict[str, int]
    coverage_limitations: tuple[str, ...]
    dataset_hash: str = Field(min_length=64, max_length=64)
    frozen: Literal[True] = True

    def hash_payload(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "sources": [item.model_dump(mode="json") for item in self.sources],
            "events": [item.model_dump(mode="json") for item in self.events],
            "controls": [item.model_dump(mode="json") for item in self.controls],
            "filters": self.filters,
            "selection_policy_version": self.selection_policy_version,
            "regions_covered": self.regions_covered,
            "years_covered": self.years_covered,
            "events_per_region": self.events_per_region,
            "coverage_limitations": self.coverage_limitations,
        }

    def verify_hash(self) -> bool:
        return canonical_hash(self.hash_payload()) == self.dataset_hash


class SplitAssignment(FrozenModel):
    member_id: str
    event_group_id: str
    role: SplitRole


class ValidationSplitManifest(FrozenModel):
    split_version: str
    dataset_version: str
    dataset_hash: str = Field(min_length=64, max_length=64)
    policy_version: str
    assignments: tuple[SplitAssignment, ...]
    counts: dict[str, int]
    created_at: datetime
    split_hash: str = Field(min_length=64, max_length=64)
    test_frozen: Literal[True] = True

    def hash_payload(self) -> dict[str, Any]:
        return {
            "split_version": self.split_version,
            "dataset_version": self.dataset_version,
            "dataset_hash": self.dataset_hash,
            "policy_version": self.policy_version,
            "assignments": [item.model_dump(mode="json") for item in self.assignments],
            "counts": self.counts,
            "test_frozen": self.test_frozen,
        }

    def verify_hash(self) -> bool:
        return canonical_hash(self.hash_payload()) == self.split_hash


class MatcherConfiguration(FrozenModel):
    matcher_version: str
    maximum_distance_m: float = Field(gt=0)
    maximum_time_gap_seconds: int = Field(gt=0)
    require_temporal_overlap: bool = False
    perimeter_mode: Literal["DISABLED", "WHEN_COMPATIBLE"] = "WHEN_COMPATIBLE"

    @property
    def configuration_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class ValidationIncident(FrozenModel):
    incident_id: str
    case_id: str
    state: Literal["VIGILANCIA", "ANOMALIA", "POSIBLE_IGNICION", "PROBABLE_INCENDIO"]
    centroid: tuple[float, float]
    first_signal_at: datetime
    last_signal_at: datetime
    source_families: tuple[str, ...]
    reference_coverage_sufficient: bool


class MatchPair(FrozenModel):
    event_id: str
    incident_id: str
    distance_m: float = Field(ge=0)
    absolute_time_gap_seconds: float = Field(ge=0)
    matcher_version: str
    configuration_hash: str = Field(min_length=64, max_length=64)


class MatchingResult(FrozenModel):
    pairs: tuple[MatchPair, ...]
    unmatched_event_ids: tuple[str, ...]
    unmatched_incident_ids: tuple[str, ...]
    unevaluable_incident_ids: tuple[str, ...]
    fragmentation_event_ids: tuple[str, ...]
    merging_incident_ids: tuple[str, ...]
    matcher_version: str
    configuration_hash: str


class EligibilityDecision(FrozenModel):
    eligible: bool
    reasons: tuple[EligibilityReason, ...]


class ConfidenceInterval(FrozenModel):
    confidence_level: float = Field(gt=0, lt=1)
    lower: float
    upper: float
    method: str


class MetricResult(FrozenModel):
    metric: str
    status: MetricStatus
    unit: str
    population: str
    n: int = Field(ge=0)
    value: float | None = None
    numerator: int | None = Field(default=None, ge=0)
    denominator: int | None = Field(default=None, ge=0)
    confidence_interval: ConfidenceInterval | None = None
    reason: str | None = None
    limitations: tuple[str, ...] = ()


class FailureRecord(FrozenModel):
    case_id: str
    event_id: str | None = None
    incident_id: str | None = None
    reason_codes: tuple[ErrorReason, ...]
    evidence: dict[str, Any]
    manual_override: Literal[False] = False


class ValidationReport(FrozenModel):
    report_version: str
    run_key: str
    dataset_version: str
    dataset_hash: str
    split_version: str
    split_hash: str
    split_role: SplitRole
    engine_versions: dict[str, str]
    matcher_version: str
    matcher_configuration_hash: str
    code_commit: str
    configuration_hash: str
    started_at: datetime
    completed_at: datetime
    sample_counts: dict[str, int]
    eligibility_counts: dict[str, int]
    excluded_counts: dict[str, int]
    metrics: tuple[MetricResult, ...]
    failures: tuple[FailureRecord, ...]
    limitations: tuple[str, ...]
    unavailable_metrics: tuple[str, ...]
    test_access_audit_id: str | None = None
    live_state_mutated: Literal[False] = False
    report_hash: str = Field(min_length=64, max_length=64)

    def hash_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"report_hash"})

    def verify_hash(self) -> bool:
        return canonical_hash(self.hash_payload()) == self.report_hash
