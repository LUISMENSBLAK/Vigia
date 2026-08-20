import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import structlog
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from vigia_geospatial.aoi import AOIRequest, resolve_inline_aoi
from vigia_geospatial.serving import render_tile, sample_raster

from .config import get_settings
from .database import DatabaseUnavailableError, VigiaDatabase
from .logging import configure_logging
from .models import (
    FireObservationCollection,
    FireObservationFeature,
    FireObservationMetadata,
    FireObservationProperties,
    GeometryPoint,
    GeospatialContextResponse,
    GeospatialCoverageCollection,
    GeospatialCoverageFeature,
    GeospatialLayerStatus,
    IncidentCollection,
    IncidentCollectionMetadata,
    IncidentDetail,
    IncidentEvidence,
    IncidentFeature,
    IncidentHistoryEntry,
    IncidentProperties,
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
            state = SourceState(str(row["service_state"]))
            detail = str(row["detail"])
            if state is SourceState.OPERATIVO and bool(row["service_check_overdue"]):
                state = SourceState.DEGRADADO
                detail = "La última comprobación del servicio excede su cadencia configurada."
            health_rows.append(
                SourceHealth(
                    source=str(row["name"]),
                    state=state,
                    checked_at=checked_at,
                    last_success_at=row["last_success_at"],
                    last_product_at=row["last_product_at"],
                    last_ingest_at=row["last_ingest_at"],
                    last_observed_at=row["last_observed_at"],
                    last_received_at=row["last_received_at"],
                    latency_seconds=row["latency_seconds"],
                    data_freshness=cast(Any, str(row["data_freshness"])),
                    service_check_overdue=bool(row["service_check_overdue"]),
                    error_code=row["error_code"],
                    detail=detail,
                )
            )
        worst = max(health_rows, key=lambda item: state_rank[item.state])
        observed_values = [item.last_observed_at for item in health_rows if item.last_observed_at]
        received_values = [item.last_received_at for item in health_rows if item.last_received_at]
        success_values = [item.last_success_at for item in health_rows if item.last_success_at]
        product_values = [item.last_product_at for item in health_rows if item.last_product_at]
        ingest_values = [item.last_ingest_at for item in health_rows if item.last_ingest_at]
        freshness_rank = {"CURRENT": 0, "UNKNOWN": 1, "NO_DATA": 2, "STALE": 3}
        freshness = max(
            (item.data_freshness for item in health_rows),
            key=lambda item: freshness_rank[item],
        )
        output.append(
            SourceHealth(
                source=configured.source,
                state=worst.state,
                checked_at=max(item.checked_at for item in health_rows if item.checked_at),
                last_success_at=max(success_values) if success_values else None,
                last_product_at=max(product_values) if product_values else None,
                last_ingest_at=max(ingest_values) if ingest_values else None,
                last_observed_at=max(observed_values) if observed_values else None,
                last_received_at=max(received_values) if received_values else None,
                latency_seconds=worst.latency_seconds,
                data_freshness=freshness,
                service_check_overdue=any(item.service_check_overdue for item in health_rows),
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


@app.get("/api/incidents", response_model=IncidentCollection, tags=["incidents"])
async def incidents(
    limit: int = Query(default=1000, ge=1, le=5000),
) -> IncidentCollection:
    generated_at = datetime.now(UTC)
    if database is None:
        return IncidentCollection(
            features=[],
            metadata=IncidentCollectionMetadata(
                data_state="SIN_DATOS",
                message="SIN INCIDENTES DERIVADOS: falta persistencia verificable.",
                count=0,
                generated_at=generated_at,
            ),
        )
    try:
        rows = await database.incidents(limit=limit)
    except DatabaseUnavailableError:
        return IncidentCollection(
            features=[],
            metadata=IncidentCollectionMetadata(
                data_state="ERROR",
                message="NO DISPONIBLE: no se pudieron consultar incidentes.",
                count=0,
                generated_at=generated_at,
            ),
        )
    features = [
        IncidentFeature(
            geometry=GeometryPoint(coordinates=(row["longitude"], row["latitude"])),
            properties=IncidentProperties(
                id=row["id"],
                code=row["code"],
                state=row["state"],
                first_signal_at=row["first_signal_at"],
                last_observation_at=row["last_observation_at"],
                observation_count=row["observation_count"],
                source_families=list(row["source_families"]),
                evidence_strength=row["evidence_strength"],
                data_quality=row["data_quality"],
                data_age_seconds=row["data_age_seconds"],
                stale=row["stale"],
            ),
        )
        for row in rows
    ]
    return IncidentCollection(
        features=features,
        metadata=IncidentCollectionMetadata(
            data_state="EXPERIMENTAL" if features else "SIN_DATOS",
            message=(
                "EXPERIMENTAL: incidentes derivados mediante reglas reproducibles."
                if features
                else "SIN INCIDENTES DERIVADOS"
            ),
            count=len(features),
            generated_at=generated_at,
        ),
    )


def _require_database() -> VigiaDatabase:
    if database is None:
        raise HTTPException(status_code=503, detail="NO DISPONIBLE: falta persistencia.")
    return database


@app.get("/api/incidents/{incident_id}", response_model=IncidentDetail, tags=["incidents"])
async def incident_detail(incident_id: UUID) -> IncidentDetail:
    active_database = _require_database()
    try:
        row = await active_database.incident(str(incident_id))
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="NO DISPONIBLE") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Incidente no encontrado.")
    explanation = row["explanation"] or {}
    return IncidentDetail(
        id=row["id"],
        code=row["code"],
        state=row["state"],
        centroid=GeometryPoint(coordinates=(row["longitude"], row["latitude"])),
        first_signal_at=row["first_signal_at"],
        last_observation_at=row["last_observation_at"],
        processed_at=row["processed_at"],
        observation_count=row["observation_count"],
        source_families=list(row["source_families"]),
        evidence_strength=row["evidence_strength"],
        reason_codes=list(row["reason_codes"]),
        explanations=list(explanation.get("why", [])),
        missing_information=list(explanation.get("missing_information", [])),
        persistence=dict(row["persistence"] or {}),
        data_quality=row["data_quality"],
        stale=row["stale"],
        rule_version=row["rule_version"],
        configuration_hash=row["configuration_hash"],
    )


@app.get(
    "/api/incidents/{incident_id}/evidence",
    response_model=list[IncidentEvidence],
    tags=["incidents"],
)
async def incident_evidence(incident_id: UUID) -> list[IncidentEvidence]:
    try:
        rows = await _require_database().incident_evidence(str(incident_id))
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="NO DISPONIBLE") from exc
    return [
        IncidentEvidence(
            observation_id=row["observation_id"],
            role=row["role"],
            source=row["source"],
            platform=row["platform"],
            sensor=row["sensor"],
            observed_at=row["observed_at"],
            received_at=row["received_at"],
            coordinates=(row["longitude"], row["latitude"]),
            confidence_raw=row["confidence_raw"],
            frp_mw=row["frp_mw"],
            brightness_kelvin=row["brightness_kelvin"],
            provenance=row["provenance"],
        )
        for row in rows
    ]


@app.get(
    "/api/incidents/{incident_id}/history",
    response_model=list[IncidentHistoryEntry],
    tags=["incidents"],
)
async def incident_history(incident_id: UUID) -> list[IncidentHistoryEntry]:
    try:
        rows = await _require_database().incident_history(str(incident_id))
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="NO DISPONIBLE") from exc
    return [
        IncidentHistoryEntry(
            previous_state=row["previous_state"],
            state=row["state"],
            changed_at=row["changed_at"],
            changed_by=row["changed_by"],
            reason_codes=[code for code in str(row["reason"] or "").split(",") if code],
            configuration_hash=row["configuration_hash"],
            software_version=row["software_version"],
            rule_version=row["rule_version"],
            commit_sha=row["commit_sha"],
        )
        for row in rows
    ]


@app.get(
    "/api/geospatial/layers",
    response_model=list[GeospatialLayerStatus],
    tags=["geospatial"],
)
async def geospatial_layers() -> list[GeospatialLayerStatus]:
    try:
        rows = await _require_database().geospatial_layers()
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="NO DISPONIBLE") from exc
    return [
        GeospatialLayerStatus(
            **row,
            message=(
                "Metadata de capa disponible; consulte cobertura y fecha."
                if row["availability"] in {"AVAILABLE", "PARTIAL"}
                else "Capa sin producto utilizable para la consulta."
            ),
        )
        for row in rows
    ]


@app.get(
    "/api/geospatial/coverage",
    response_model=GeospatialCoverageCollection,
    tags=["geospatial"],
)
async def geospatial_coverage(
    west: float | None = Query(default=None, ge=-180, le=180),
    south: float | None = Query(default=None, ge=-90, le=90),
    east: float | None = Query(default=None, ge=-180, le=180),
    north: float | None = Query(default=None, ge=-90, le=90),
    geojson: str | None = Query(default=None, max_length=20_000),
    administrative_area: str | None = Query(default=None, min_length=1, max_length=160),
    as_of: datetime | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> GeospatialCoverageCollection:
    cutoff = as_of or datetime.now(UTC)
    bbox_items = (west, south, east, north)
    has_any_bbox = any(item is not None for item in bbox_items)
    has_complete_bbox = all(item is not None for item in bbox_items)
    if has_any_bbox and not has_complete_bbox:
        raise HTTPException(status_code=422, detail="bbox requiere west, south, east y north.")
    selector_count = sum((has_complete_bbox, geojson is not None, administrative_area is not None))
    if selector_count != 1:
        raise HTTPException(status_code=422, detail="Seleccione exactamente una AOI.")
    bbox: tuple[float, float, float, float] | None = None
    geometry_geojson: str | None = None
    try:
        if has_complete_bbox:
            assert west is not None and south is not None and east is not None and north is not None
            bbox = (west, south, east, north)
            resolve_inline_aoi(AOIRequest(bbox=bbox))
        elif geojson is not None:
            parsed_geojson = json.loads(geojson)
            if not isinstance(parsed_geojson, dict):
                raise ValueError("GeoJSON debe ser un objeto.")
            resolved = resolve_inline_aoi(AOIRequest(geojson=parsed_geojson))
            geometry_geojson = json.dumps(resolved.geojson, separators=(",", ":"))
        else:
            AOIRequest(administrative_area=administrative_area)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        rows = await _require_database().geospatial_coverage(
            bbox=bbox,
            geometry_geojson=geometry_geojson,
            administrative_area=administrative_area,
            as_of=cutoff,
            limit=limit,
        )
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="NO DISPONIBLE") from exc
    return GeospatialCoverageCollection(
        as_of=cutoff,
        features=[
            GeospatialCoverageFeature(
                geometry=row.pop("geometry"),
                properties=row,
            )
            for row in rows
        ],
    )


@app.get(
    "/api/geospatial/context",
    response_model=GeospatialContextResponse,
    tags=["geospatial"],
)
async def geospatial_context(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    as_of: datetime | None = None,
) -> GeospatialContextResponse:
    cutoff = as_of or datetime.now(UTC)
    try:
        rows = await _require_database().geospatial_context(
            longitude=lon, latitude=lat, as_of=cutoff
        )
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="NO DISPONIBLE") from exc
    categories: dict[str, dict[str, Any]] = {
        "terrain": {},
        "vegetation": {},
        "land_cover": {},
        "lidar": {},
    }
    provenance: list[dict[str, Any]] = []
    terrain_layers = {"ELEVATION", "SLOPE", "ASPECT", "TERRAIN_RUGGEDNESS"}
    vegetation_layers = {"NDVI", "NDMI", "NBR", "FUEL_PROXY"}
    lidar_layers = {"LIDAR_DTM", "LIDAR_DSM", "CANOPY_HEIGHT"}
    for row in rows:
        layer = row["layer"]
        if layer in terrain_layers:
            context_category = "terrain"
        elif layer in vegetation_layers:
            context_category = "vegetation"
        elif layer in lidar_layers:
            context_category = "lidar"
        else:
            context_category = "land_cover"
        categories[context_category][layer.casefold()] = {
            "value": None,
            "message": "NO DISPONIBLE",
            "availability": row["availability"],
            "observed_at": row["observed_at"],
            "processed_at": row["processed_at"],
            "resolution_m": row["output_resolution_m"],
            "source": row["source"],
            "product_id": row["product_id"],
            "quality": row["quality"],
        }
        entry = categories[context_category][layer.casefold()]
        if row.get("vector_value") is not None:
            entry["value"] = row["vector_value"]
            entry["message"] = "Valor vectorial oficial disponible para el punto."
        elif row.get("storage_uri") and row.get("raster_band"):
            try:
                value = sample_raster(
                    str(row["storage_uri"]),
                    longitude=lon,
                    latitude=lat,
                    band=int(row["raster_band"]),
                    storage_root=Path(settings.GEOSPATIAL_STORAGE_ROOT),
                )
            except ValueError:
                value = None
            if value is not None:
                entry["value"] = value
                entry["units"] = row["value_units"]
                entry["message"] = "Valor muestreado del COG materializado."
        provenance.append({"product_id": row["product_id"], "provenance_id": row["provenance_id"]})
    for category_payload in categories.values():
        if not category_payload:
            category_payload.update({"availability": "UNAVAILABLE", "message": "NO DISPONIBLE"})
    return GeospatialContextResponse(
        longitude=lon,
        latitude=lat,
        as_of=cutoff,
        provenance=provenance,
        **categories,
    )


@app.get("/api/geospatial/tiles/{product_id}/{z}/{x}/{y}.png", tags=["geospatial"])
async def geospatial_tile(product_id: UUID, z: int, x: int, y: int) -> Response:
    if z < 0 or z > 18:
        raise HTTPException(status_code=422, detail="Nivel de zoom fuera de rango.")
    try:
        row = await _require_database().geospatial_product(str(product_id))
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="NO DISPONIBLE") from exc
    if row is None or not row["storage_uri"] or not row["raster_band"]:
        raise HTTPException(status_code=404, detail="Tesela NO DISPONIBLE.")
    try:
        content = render_tile(
            str(row["storage_uri"]),
            band=int(row["raster_band"]),
            layer=str(row["layer"]),
            z=z,
            x=x,
            y=y,
            storage_root=Path(settings.GEOSPATIAL_STORAGE_ROOT),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Tesela NO DISPONIBLE.") from exc
    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
