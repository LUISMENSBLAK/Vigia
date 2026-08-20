from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceState(StrEnum):
    OPERATIVO = "OPERATIVO"
    DEGRADADO = "DEGRADADO"
    SIN_DATOS = "SIN_DATOS"
    ERROR = "ERROR"


class SourceHealth(BaseModel):
    source: str
    state: SourceState
    checked_at: datetime | None = None
    last_observed_at: datetime | None = None
    last_received_at: datetime | None = None
    latency_seconds: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    detail: str


class SystemStatus(BaseModel):
    generated_at: datetime
    mode: str
    sources: list[SourceHealth]


class GeometryPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class FireObservationProperties(BaseModel):
    id: str
    source: str
    platform: str
    sensor: str
    observed_at: datetime
    received_at: datetime
    confidence_raw: str | None = None
    brightness_kelvin: float | None = None
    frp_mw: float | None = None
    daynight: str | None = None
    age_seconds: int = Field(ge=0)
    provenance: dict[str, Any] | None = None


class FireObservationFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: GeometryPoint
    properties: FireObservationProperties


class FireObservationMetadata(BaseModel):
    data_state: SourceState
    message: str
    count: int = Field(ge=0)
    generated_at: datetime


class FireObservationCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[FireObservationFeature]
    metadata: FireObservationMetadata


class IncidentProperties(BaseModel):
    id: str
    code: str
    state: str
    first_signal_at: datetime
    last_observation_at: datetime
    observation_count: int = Field(ge=0)
    source_families: list[str]
    evidence_strength: str | None = None
    data_quality: str
    data_age_seconds: int = Field(ge=0)
    stale: bool


class IncidentFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: GeometryPoint
    properties: IncidentProperties


class IncidentCollectionMetadata(BaseModel):
    data_state: Literal["EXPERIMENTAL", "SIN_DATOS", "ERROR"]
    message: str
    count: int = Field(ge=0)
    generated_at: datetime


class IncidentCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[IncidentFeature]
    metadata: IncidentCollectionMetadata


class IncidentDetail(BaseModel):
    id: str
    code: str
    state: str
    centroid: GeometryPoint
    first_signal_at: datetime
    last_observation_at: datetime
    processed_at: datetime | None = None
    observation_count: int = Field(ge=0)
    source_families: list[str]
    evidence_strength: str | None = None
    reason_codes: list[str]
    explanations: list[str]
    missing_information: list[str]
    persistence: dict[str, Any]
    data_quality: str
    stale: bool
    rule_version: str | None = None
    configuration_hash: str | None = None


class IncidentEvidence(BaseModel):
    observation_id: str
    role: Literal["confirming", "contradicting", "context"]
    source: str
    platform: str
    sensor: str
    observed_at: datetime
    received_at: datetime
    coordinates: tuple[float, float]
    confidence_raw: str | None = None
    frp_mw: float | None = None
    brightness_kelvin: float | None = None
    provenance: dict[str, Any] | None = None


class IncidentHistoryEntry(BaseModel):
    previous_state: str | None = None
    state: str
    changed_at: datetime
    changed_by: str
    reason_codes: list[str]
    configuration_hash: str | None = None
    software_version: str | None = None
    rule_version: str | None = None
    commit_sha: str | None = None


def current_status(
    *,
    live_enabled: bool,
    database_configured: bool,
    firms_configured: bool,
    aemet_configured: bool,
    eumetsat_configured: bool,
    copernicus_configured: bool,
) -> SystemStatus:
    sources = [
        SourceHealth(
            source="NASA FIRMS",
            state=SourceState.SIN_DATOS,
            detail=(
                "Credencial configurada; todavía no existe una ingestión verificada."
                if firms_configured
                else "Falta NASA_FIRMS_MAP_KEY."
            ),
        ),
        SourceHealth(source="AEMET", state=SourceState.SIN_DATOS, detail="Worker pendiente."),
        SourceHealth(source="EUMETSAT", state=SourceState.SIN_DATOS, detail="Worker pendiente."),
        SourceHealth(source="Copernicus", state=SourceState.SIN_DATOS, detail="Worker pendiente."),
        SourceHealth(
            source="Supabase / PostGIS",
            state=SourceState.SIN_DATOS,
            detail=(
                "Conexión configurada; todavía no verificada."
                if database_configured
                else "Falta SUPABASE_DB_URL."
            ),
        ),
        SourceHealth(
            source="Workers", state=SourceState.SIN_DATOS, detail="Sin ejecución verificada."
        ),
    ]
    configured_details = {
        "AEMET": (aemet_configured, "AEMET_API_KEY"),
        "EUMETSAT": (eumetsat_configured, "EUMETSAT_CONSUMER_KEY y EUMETSAT_CONSUMER_SECRET"),
        "Copernicus": (
            copernicus_configured,
            "COPERNICUS_CLIENT_ID y COPERNICUS_CLIENT_SECRET",
        ),
    }
    for source in sources:
        configuration = configured_details.get(source.source)
        if configuration is not None:
            configured, variables = configuration
            source.detail = (
                "Credenciales configuradas; todavía no existe una comprobación verificada."
                if configured
                else f"Falta {variables}."
            )
    return SystemStatus(
        generated_at=datetime.now(UTC),
        mode="LIVE" if live_enabled else "DEMO",
        sources=sources,
    )
