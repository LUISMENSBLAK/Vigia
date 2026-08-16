from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceState(StrEnum):
    OPERATIVO = "OPERATIVO"
    DEGRADADO = "DEGRADADO"
    SIN_DATOS = "SIN_DATOS"
    ERROR = "ERROR"


class SourceHealth(BaseModel):
    source: str
    state: SourceState
    last_received_at: datetime | None = None
    latency_seconds: int | None = Field(default=None, ge=0)
    detail: str


class SystemStatus(BaseModel):
    generated_at: datetime
    mode: str
    sources: list[SourceHealth]


def current_status(*, live_enabled: bool, firms_configured: bool) -> SystemStatus:
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
            source="Database",
            state=SourceState.SIN_DATOS,
            detail="Sin conexión verificada.",
        ),
    ]
    return SystemStatus(
        generated_at=datetime.now(UTC),
        mode="LIVE" if live_enabled else "DEMO",
        sources=sources,
    )
