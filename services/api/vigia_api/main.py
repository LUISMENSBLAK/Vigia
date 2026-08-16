from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog
from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import DatabaseUnavailableError, VigiaDatabase
from .logging import configure_logging
from .models import (
    FireObservationCollection,
    FireObservationFeature,
    FireObservationMetadata,
    FireObservationProperties,
    GeometryPoint,
    SourceHealth,
    SourceState,
    SystemStatus,
    current_status,
)

settings = get_settings()
configure_logging(settings.LOG_LEVEL)
logger = structlog.get_logger()
database = (
    VigiaDatabase(settings.SUPABASE_DB_URL.get_secret_value())
    if settings.SUPABASE_DB_URL is not None
    else None
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("api_started", app=settings.APP_NAME, environment=settings.APP_ENV)
    yield
    if database is not None:
        await database.close()
    logger.info("api_stopped")


app = FastAPI(
    title="VIGÍA API",
    description="API científica y geoespacial de VIGÍA.",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "vigia-api"}


def _configuration_status() -> SystemStatus:
    return current_status(
        live_enabled=settings.VIGIA_ENABLE_LIVE_DATA,
        database_configured=database is not None,
        firms_configured=settings.NASA_FIRMS_MAP_KEY is not None,
        aemet_configured=settings.AEMET_API_KEY is not None,
        eumetsat_configured=(
            settings.EUMETSAT_CONSUMER_KEY is not None
            and settings.EUMETSAT_CONSUMER_SECRET is not None
        ),
        copernicus_configured=(
            settings.COPERNICUS_CLIENT_ID is not None
            and settings.COPERNICUS_CLIENT_SECRET is not None
        ),
    )


def _public_group(code: str) -> str | None:
    if code.startswith("NASA_FIRMS_"):
        return "NASA FIRMS"
    if code == "AEMET_OPEN_DATA":
        return "AEMET"
    if code == "EUMETSAT_MTG_FCI_AFM":
        return "EUMETSAT"
    if code.startswith("COPERNICUS_SENTINEL_"):
        return "Copernicus"
    return None


def _aggregate_health(rows: list[dict[str, Any]], fallback: SystemStatus) -> list[SourceHealth]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        group = _public_group(str(row["code"]))
        if group is not None:
            grouped.setdefault(group, []).append(row)

    output: list[SourceHealth] = []
    now = datetime.now(UTC)
    state_rank = {
        SourceState.OPERATIVO: 0,
        SourceState.SIN_DATOS: 1,
        SourceState.DEGRADADO: 2,
        SourceState.ERROR: 3,
    }
    for configured in fallback.sources:
        candidates = grouped.get(configured.source)
        if not candidates:
            output.append(configured)
            continue
        health_rows: list[SourceHealth] = []
        for row in candidates:
            checked_at = row["checked_at"]
            state = SourceState(str(row["state"]))
            detail = str(row["detail"])
            if state is SourceState.OPERATIVO and now - checked_at > timedelta(minutes=15):
                state = SourceState.DEGRADADO
                detail = "Última comprobación correcta con más de 15 minutos de antigüedad."
            health_rows.append(
                SourceHealth(
                    source=str(row["name"]),
                    state=state,
                    checked_at=checked_at,
                    last_observed_at=row["last_observed_at"],
                    last_received_at=row["last_received_at"],
                    latency_seconds=row["latency_seconds"],
                    error_code=row["error_code"],
                    detail=detail,
                )
            )
        worst = max(health_rows, key=lambda item: state_rank[item.state])
        observed_values = [item.last_observed_at for item in health_rows if item.last_observed_at]
        received_values = [item.last_received_at for item in health_rows if item.last_received_at]
        output.append(
            SourceHealth(
                source=configured.source,
                state=worst.state,
                checked_at=max(item.checked_at for item in health_rows if item.checked_at),
                last_observed_at=max(observed_values) if observed_values else None,
                last_received_at=max(received_values) if received_values else None,
                latency_seconds=worst.latency_seconds,
                error_code=worst.error_code,
                detail=worst.detail,
            )
        )
    return output


def _worker_health(row: dict[str, Any] | None) -> SourceHealth:
    if row is None:
        return SourceHealth(
            source="Workers", state=SourceState.SIN_DATOS, detail="Sin ejecución registrada."
        )
    state = str(row["state"])
    checked_at = row["finished_at"] or row["started_at"]
    if state == "SUCCEEDED":
        recent = datetime.now(UTC) - checked_at <= timedelta(minutes=15)
        return SourceHealth(
            source="Workers",
            state=SourceState.OPERATIVO if recent else SourceState.DEGRADADO,
            checked_at=checked_at,
            last_received_at=row["finished_at"],
            detail=(
                f"Última ingestión completada: {row['source']} "
                f"({row['records_written']}/{row['records_received']} registros escritos)."
            ),
        )
    if state == "RUNNING":
        return SourceHealth(
            source="Workers",
            state=SourceState.DEGRADADO,
            checked_at=checked_at,
            detail=f"Ingestión en curso para {row['source']}; todavía no verificada.",
        )
    return SourceHealth(
        source="Workers",
        state=SourceState.DEGRADADO if state == "PARTIAL" else SourceState.ERROR,
        checked_at=checked_at,
        last_received_at=row["finished_at"],
        error_code=f"INGEST_{state}",
        detail=f"Última ingestión {state} para {row['source']}.",
    )


@app.get("/v1/status", response_model=SystemStatus, tags=["system"])
async def status() -> SystemStatus:
    fallback = _configuration_status()
    if database is None:
        return fallback
    try:
        database_health = await database.health()
        rows = await database.source_health()
        latest_ingest = await database.latest_ingest_run()
    except DatabaseUnavailableError:
        for source in fallback.sources:
            if source.source == "Supabase / PostGIS":
                source.state = SourceState.ERROR
                source.checked_at = datetime.now(UTC)
                source.error_code = "DATABASE_UNAVAILABLE"
                source.detail = "No se pudo verificar Supabase/PostGIS."
        return fallback

    sources = _aggregate_health(rows, fallback)
    for source in sources:
        if source.source == "Supabase / PostGIS":
            source.state = SourceState.OPERATIVO
            source.checked_at = database_health.checked_at
            source.detail = f"PostGIS verificado ({database_health.postgis_version})."
        elif source.source == "Workers":
            worker = _worker_health(latest_ingest)
            source.state = worker.state
            source.checked_at = worker.checked_at
            source.last_received_at = worker.last_received_at
            source.error_code = worker.error_code
            source.detail = worker.detail
    return SystemStatus(generated_at=datetime.now(UTC), mode=fallback.mode, sources=sources)


@app.get(
    "/v1/fire-observations",
    response_model=FireObservationCollection,
    tags=["observations"],
)
async def fire_observations(
    limit: int = Query(default=5000, ge=1, le=5000),
) -> FireObservationCollection:
    generated_at = datetime.now(UTC)
    if database is None:
        return FireObservationCollection(
            features=[],
            metadata=FireObservationMetadata(
                data_state=SourceState.SIN_DATOS,
                message="Falta SUPABASE_DB_URL; no existe persistencia verificable.",
                count=0,
                generated_at=generated_at,
            ),
        )
    try:
        rows = await database.fire_observations(limit=limit)
    except DatabaseUnavailableError:
        return FireObservationCollection(
            features=[],
            metadata=FireObservationMetadata(
                data_state=SourceState.ERROR,
                message="NO DISPONIBLE: no se pudo consultar Supabase/PostGIS.",
                count=0,
                generated_at=generated_at,
            ),
        )

    features = [
        FireObservationFeature(
            geometry=GeometryPoint(coordinates=(row["longitude"], row["latitude"])),
            properties=FireObservationProperties(
                id=row["id"],
                source=row["source"],
                platform=row["platform"],
                sensor=row["sensor"],
                observed_at=row["observed_at"],
                received_at=row["received_at"],
                confidence_raw=row["confidence_raw"],
                brightness_kelvin=row["brightness_kelvin"],
                frp_mw=row["frp_mw"],
                daynight=row["daynight"],
                age_seconds=row["age_seconds"],
                provenance=row["provenance"],
            ),
        )
        for row in rows
    ]
    state = SourceState.OPERATIVO if features else SourceState.SIN_DATOS
    message = (
        "Observaciones térmicas persistidas y trazables."
        if features
        else "SIN OBSERVACIONES ACTIVAS"
    )
    return FireObservationCollection(
        features=features,
        metadata=FireObservationMetadata(
            data_state=state,
            message=message,
            count=len(features),
            generated_at=generated_at,
        ),
    )
