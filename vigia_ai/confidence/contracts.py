from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EvidenceDescriptor(BaseModel):
    observation_id: str
    source: str
    platform: str
    sensor: str
    independence_group: str
    observed_at: datetime
    age_seconds: int = Field(ge=0)
    resolution_m: float | None = Field(default=None, gt=0)
    persistence_count: int = Field(ge=1)
    confidence_raw: str | None = None
    input_hash: str
    source_family: str | None = None
    evidence_role: Literal["confirming", "contradicting", "context"] = "confirming"
    quality: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    candidate_id: str
    evidence: list[EvidenceDescriptor]
    source_families: list[str]
    approximate_independence_note: str
    persistence_seconds: int = Field(ge=0)
    spatial_extent_m: float = Field(ge=0)
    meteorology_available: bool
    vegetation_available: bool
    known_heat_source_match: bool
    contradiction_count: int = Field(ge=0)
    configuration_hash: str


class ResearchConfidenceAssessment(BaseModel):
    status: Literal["research"] = "research"
    engine_version: str
    evidence: list[EvidenceDescriptor]
    bundle: EvidenceBundle | None = None
    spatial_consistency_evaluated: bool
    temporal_consistency_evaluated: bool
    meteorology_evaluated: bool
    vegetation_evaluated: bool
    contradictions_evaluated: bool
    calibrated_probability: None = None
    limitation: str = (
        "Arquitectura sin calibración ni validación; no produce una probabilidad operativa."
    )


REQUIRED_CONFIDENCE_DIMENSIONS = (
    "independence",
    "correlation",
    "age",
    "resolution",
    "persistence",
    "temporal_consistency",
    "spatial_consistency",
    "meteorology",
    "vegetation",
    "contradictions",
)
