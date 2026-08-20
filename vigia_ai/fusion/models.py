from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SourceFamily(StrEnum):
    NASA_VIIRS = "NASA_VIIRS"
    NASA_MODIS = "NASA_MODIS"
    EUMETSAT_MTG = "EUMETSAT_MTG"
    COPERNICUS_OPTICAL = "COPERNICUS_OPTICAL"
    COPERNICUS_RADAR = "COPERNICUS_RADAR"
    COPERNICUS_THERMAL = "COPERNICUS_THERMAL"
    AEMET_WEATHER = "AEMET_WEATHER"
    TERRAIN = "TERRAIN"
    VEGETATION = "VEGETATION"
    UNKNOWN = "UNKNOWN"


THERMAL_SOURCE_FAMILIES = frozenset(
    {
        SourceFamily.NASA_VIIRS,
        SourceFamily.NASA_MODIS,
        SourceFamily.EUMETSAT_MTG,
        SourceFamily.COPERNICUS_THERMAL,
    }
)


class EvidenceRole(StrEnum):
    CONFIRMING = "confirming"
    CONTRADICTING = "contradicting"
    CONTEXT = "context"


class DataQuality(StrEnum):
    COMPLETA = "COMPLETA"
    PARCIAL = "PARCIAL"
    DEGRADADA = "DEGRADADA"
    DESCONOCIDA = "DESCONOCIDA"


class EvidenceStrength(StrEnum):
    MUY_BAJA = "MUY_BAJA"
    BAJA = "BAJA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    MUY_ALTA = "MUY_ALTA"


class ObservationEvidence(BaseModel):
    observation_id: str
    source: str
    provider: str
    platform: str
    sensor: str
    observed_at: datetime
    received_at: datetime
    processed_at: datetime | None = None
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    spatial_resolution_m: float | None = Field(default=None, gt=0)
    temporal_age_seconds: int = Field(ge=0)
    confidence_raw: str | None = None
    fire_probability: float | None = Field(default=None, ge=0, le=1)
    frp_mw: float | None = Field(default=None, ge=0)
    brightness_kelvin: float | None = Field(default=None, ge=0)
    daynight: Literal["D", "N"] | None = None
    quality: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] | None = None
    source_family: SourceFamily

    @model_validator(mode="after")
    def timestamps_are_ordered(self) -> "ObservationEvidence":
        if self.received_at < self.observed_at:
            raise ValueError("received_at no puede ser anterior a observed_at")
        if self.processed_at is not None and self.processed_at < self.received_at:
            raise ValueError("processed_at no puede ser anterior a received_at")
        return self

    @property
    def source_latency_seconds(self) -> int:
        return max(0, int((self.received_at - self.observed_at).total_seconds()))

    @property
    def processing_latency_seconds(self) -> int | None:
        if self.processed_at is None:
            return None
        return max(0, int((self.processed_at - self.received_at).total_seconds()))

    @property
    def total_latency_seconds(self) -> int | None:
        if self.processed_at is None:
            return None
        return max(0, int((self.processed_at - self.observed_at).total_seconds()))


class EvidenceItem(BaseModel):
    observation: ObservationEvidence
    role: EvidenceRole
    reason_codes: tuple[str, ...] = ()


class PersistenceMetrics(BaseModel):
    detection_count: int = Field(ge=1)
    consecutive_windows: int = Field(ge=1)
    persistence_seconds: int = Field(ge=0)
    temporal_gap_max_seconds: int = Field(ge=0)
    temporal_gap_mean_seconds: float = Field(ge=0)


class IncidentCandidate(BaseModel):
    candidate_id: str
    observations: tuple[EvidenceItem, ...]
    first_observation_at: datetime
    last_observation_at: datetime
    centroid: tuple[float, float]
    spatial_extent_m: float = Field(ge=0)
    platforms: tuple[str, ...]
    sensors: tuple[str, ...]
    source_families: tuple[SourceFamily, ...]
    persistence: PersistenceMetrics
    data_quality: DataQuality
    configuration_hash: str

    @property
    def confirming_count(self) -> int:
        return sum(item.role is EvidenceRole.CONFIRMING for item in self.observations)

    @property
    def contradicting_count(self) -> int:
        return sum(item.role is EvidenceRole.CONTRADICTING for item in self.observations)


class FusionRunSummary(BaseModel):
    as_of: datetime
    configuration_hash: str
    input_observation_count: int = Field(ge=0)
    eligible_observation_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    incident_candidate_count: int = Field(ge=0)
    candidates: tuple[IncidentCandidate, ...]
