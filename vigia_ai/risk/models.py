from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class RiskMode(StrEnum):
    ANALYSIS = "ANALYSIS"
    FORECAST = "FORECAST"


class RiskDataQuality(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT_DATA"


class RiskAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    PROCESSING = "PROCESSING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class FWIState:
    ffmc: float
    dmc: float
    dc: float


@dataclass(frozen=True, slots=True)
class FWIWeather:
    observed_at: datetime
    temperature_c: float
    relative_humidity_pct: float
    wind_speed_kmh: float
    precipitation_24h_mm: float


@dataclass(frozen=True, slots=True)
class FWIResult:
    observed_at: datetime
    ffmc: float
    dmc: float
    dc: float
    isi: float
    bui: float
    fwi: float

    @property
    def state(self) -> FWIState:
        return FWIState(ffmc=self.ffmc, dmc=self.dmc, dc=self.dc)


@dataclass(frozen=True, slots=True)
class ComponentEvidence:
    name: str
    score: float | None
    observed_at: datetime | None
    source: str
    resolution_m: float | None
    quality: RiskDataQuality
    reason_codes: tuple[str, ...] = ()
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    engine_version: str
    mode: RiskMode
    as_of: datetime
    valid_at: datetime
    horizon_hours: int
    experimental_index: float | None
    risk_class: str
    data_quality: RiskDataQuality
    components: tuple[ComponentEvidence, ...]
    missing_components: tuple[str, ...]
    reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]
    disclaimer: str = (
        "Índice ambiental experimental; no es una probabilidad de incendio ni confirma fuego."
    )
