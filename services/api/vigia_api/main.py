from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .logging import configure_logging
from .models import SystemStatus, current_status

settings = get_settings()
configure_logging(settings.LOG_LEVEL)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("api_started", app=settings.APP_NAME, environment=settings.APP_ENV)
    yield
    logger.info("api_stopped")


app = FastAPI(
    title="VIGÍA API",
    description="API científica y geoespacial de VIGÍA.",
    version="0.1.0",
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


@app.get("/v1/status", response_model=SystemStatus, tags=["system"])
async def status() -> SystemStatus:
    return current_status(
        live_enabled=settings.VIGIA_ENABLE_LIVE_DATA,
        firms_configured=bool(settings.NASA_FIRMS_MAP_KEY),
    )


@app.get("/v1/fire-observations", tags=["observations"])
async def fire_observations() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [],
        "metadata": {
            "data_state": "SIN_DATOS",
            "message": "No existe una ingestión FIRMS verificada.",
            "provenance": [],
        },
    }
