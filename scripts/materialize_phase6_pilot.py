from __future__ import annotations

import argparse
import asyncio
import json
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from services.api.vigia_api.config import get_settings
from services.api.vigia_api.database import VigiaDatabase
from vigia_ai.fusion.config import load_fusion_config
from vigia_ai.historical.jcyl import JcylHistoricalClient, build_jcyl_corpus, select_pilot_events
from vigia_ai.historical.repository import HistoricalCorpusRepository
from vigia_ai.replay.clock import ReplayClock
from vigia_ai.replay.context import ReplayDataContext
from vigia_ai.replay.engine import ReplayEngine
from vigia_ai.replay.models import ReplayCaseManifest, ReplayInput, ReplayInputKind
from vigia_ai.replay.repository import ReplayRepository
from workers.aemet.client import AemetClient
from workers.copernicus.client import SENTINEL_COLLECTIONS, CopernicusClient
from workers.firms.vigia_firms.client import FirmsClient, FirmsObservation, FirmsSource

AVAILABILITY_CONFIG = Path("config/replay/sensor-availability-v1.json")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materializa y ejecuta el corpus piloto Fase 6")
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--pilot-rank", type=int, default=0)
    parser.add_argument("--pilot-limit", type=int, default=12)
    parser.add_argument("--step-minutes", type=int, default=10)
    return parser.parse_args()


def _bbox(longitude: float, latitude: float) -> tuple[float, float, float, float]:
    # AOI de investigación amplia alrededor del origen oficial. No es el perímetro final.
    return (longitude - 0.6, latitude - 0.45, longitude + 0.6, latitude + 0.45)


def _aoi_geojson(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    west, south, east, north = bbox
    return {
        "type": "MultiPolygon",
        "coordinates": [
            [[[west, south], [east, south], [east, north], [west, north], [west, south]]]
        ],
    }


def _source_family(source: FirmsSource) -> str:
    return "NASA_MODIS" if source is FirmsSource.MODIS_SP else "NASA_VIIRS"


def _resolution(source: FirmsSource) -> float:
    return 1000.0 if source is FirmsSource.MODIS_SP else 375.0


def _thermal_input(observation: FirmsObservation) -> ReplayInput:
    return ReplayInput(
        input_id=observation.external_id,
        kind=ReplayInputKind.THERMAL_OBSERVATION,
        source=observation.source.catalogue_code,
        observed_at=observation.acquired_at,
        # FIRMS archive does not expose the original publication timestamp. The observation
        # timestamp is retained as an explicit lower-bound proxy; latency claims are prohibited.
        available_at=observation.acquired_at,
        longitude=observation.longitude,
        latitude=observation.latitude,
        payload={
            "provider": "NASA LANCE FIRMS",
            "platform": observation.satellite,
            "sensor": observation.instrument,
            "spatial_resolution_m": _resolution(observation.source),
            "confidence_raw": observation.confidence,
            "frp_mw": observation.frp,
            "brightness_kelvin": observation.brightness,
            "daynight": observation.daynight,
            "source_family": _source_family(observation.source),
        },
        provenance={
            "provider": "NASA LANCE FIRMS",
            "dataset": observation.source.value,
            "processing": "standard",
            "raw_properties": observation.raw_properties,
        },
        availability_basis="OBSERVATION_TIME_PROXY",
        quality_flags=(
            "HISTORICAL_AVAILABILITY_TIME_NOT_EXPOSED",
            "NO_LATENCY_CLAIMS_ALLOWED",
        ),
    )


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def _sentinel_inputs(payload: dict[str, Any], *, cutoff: datetime) -> list[ReplayInput]:
    output: list[ReplayInput] = []
    features = payload.get("features")
    if not isinstance(features, list):
        return output
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            continue
        properties = feature["properties"]
        observed_at = _parse_datetime(properties.get("datetime"))
        available_at = _parse_datetime(properties.get("created"))
        product_id = feature.get("id")
        if (
            observed_at is None
            or available_at is None
            or available_at > cutoff
            or not isinstance(product_id, str)
        ):
            continue
        output.append(
            ReplayInput(
                input_id=f"sentinel-2-{product_id}",
                kind=ReplayInputKind.SENTINEL_PRODUCT,
                source="COPERNICUS_SENTINEL_2",
                observed_at=observed_at,
                available_at=max(observed_at, available_at),
                payload={
                    "product_id": product_id,
                    "cloud_cover": properties.get("eo:cloud_cover"),
                    "collection": feature.get("collection"),
                },
                provenance={
                    "provider": "Copernicus Data Space Ecosystem",
                    "feature": feature,
                },
                availability_basis="PUBLISHED",
            )
        )
    return output


def _sensor_availability(event_time: datetime) -> dict[str, str]:
    config = json.loads(AVAILABILITY_CONFIG.read_text(encoding="utf-8"))
    output: dict[str, str] = {}
    for sensor, metadata in config["sensors"].items():
        available_from = _parse_datetime(metadata["available_from"])
        output[sensor] = (
            "AVAILABLE_AT_EVENT_TIME"
            if available_from is not None and event_time >= available_from
            else "NOT_AVAILABLE_AT_EVENT_TIME"
        )
    return output


async def run() -> None:
    args = arguments()
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None or settings.NASA_FIRMS_MAP_KEY is None:
        raise SystemExit("NO DISPONIBLE: faltan PostgreSQL o NASA_FIRMS_MAP_KEY")
    retrieved_at = datetime.now(UTC)
    payload = await JcylHistoricalClient().fetch()
    events = build_jcyl_corpus(payload, retrieved_at=retrieved_at)
    pilot = select_pilot_events(events, limit=args.pilot_limit)
    if not pilot or not 0 <= args.pilot_rank < len(pilot):
        raise SystemExit("NO DISPONIBLE: el criterio piloto no produjo el rango solicitado")
    event = pilot[args.pilot_rank]
    start_reference = event.official_start
    if (
        start_reference is None
        or start_reference.instant is None
        or event.longitude is None
        or event.latitude is None
    ):
        raise SystemExit("NO DISPONIBLE: el caso piloto carece de tiempo/coordenadas precisos")
    reference_time = start_reference.instant
    replay_start = reference_time - timedelta(hours=3)
    replay_end = reference_time + timedelta(hours=30)
    bbox = _bbox(event.longitude, event.latitude)

    firms = FirmsClient(settings.NASA_FIRMS_MAP_KEY.get_secret_value(), timeout_seconds=90)
    observations: list[FirmsObservation] = []
    first_date = replay_start.date()
    day_range = min(5, (replay_end.date() - first_date).days + 1)
    for source in (
        FirmsSource.VIIRS_NOAA20_SP,
        FirmsSource.VIIRS_SNPP_SP,
        FirmsSource.MODIS_SP,
    ):
        observations.extend(
            await firms.fetch_area(
                source,
                bbox=bbox,
                day_range=day_range,
                end_date=first_date,
                received_at=retrieved_at,
            )
        )
    inputs = [
        _thermal_input(item)
        for item in observations
        if replay_start <= item.acquired_at <= replay_end
    ]

    aemet_status = "UNAVAILABLE"
    aemet_records = 0
    if settings.AEMET_API_KEY is not None:
        daily = await AemetClient(
            settings.AEMET_API_KEY.get_secret_value(), timeout_seconds=90
        ).fetch_daily_climate(
            start_date=(reference_time - timedelta(days=8)).date(),
            end_date=reference_time.date(),
        )
        provinces = {item.replace("Ó", "O") for item in event.province}
        relevant_daily = [item for item in daily if item.province in provinces]
        aemet_records = len(relevant_daily)
        aemet_status = (
            "PARTIAL_DATE_ONLY_NOT_FWI_READY" if relevant_daily else "UNAVAILABLE"
        )

    sentinel_status = "UNAVAILABLE"
    if (
        settings.COPERNICUS_CLIENT_ID is not None
        and settings.COPERNICUS_CLIENT_SECRET is not None
    ):
        copernicus = CopernicusClient(
            settings.COPERNICUS_CLIENT_ID.get_secret_value(),
            settings.COPERNICUS_CLIENT_SECRET.get_secret_value(),
            token_url=settings.COPERNICUS_TOKEN_URL,
            base_url=settings.COPERNICUS_SH_BASE_URL,
            timeout_seconds=60,
        )
        catalog = await copernicus.catalog_search(
            collection=SENTINEL_COLLECTIONS["sentinel-2"],
            bbox=bbox,
            start=reference_time - timedelta(days=30),
            end=reference_time,
            limit=50,
        )
        sentinel = _sentinel_inputs(catalog, cutoff=reference_time)
        inputs.extend(sentinel)
        sentinel_status = "AVAILABLE" if sentinel else "UNAVAILABLE"

    unique_inputs = tuple({item.input_id: item for item in inputs}.values())
    available_sources = tuple(sorted({item.source for item in unique_inputs}))
    sensor_availability = _sensor_availability(reference_time)
    sensor_availability["AEMET_DAILY"] = aemet_status
    sensor_availability["SENTINEL_2"] = sentinel_status
    sensor_availability["MTG_FCI_AUTHENTICATION"] = "UNAVAILABLE_INVALID_CLIENT"
    case_id = f"REPLAY-{event.vigia_code}-V1"
    manifest = ReplayCaseManifest(
        case_id=case_id,
        historical_fire_event_id=event.event_key,
        case_kind="POSITIVE_REFERENCE",
        aoi_geojson=_aoi_geojson(bbox),
        replay_start=replay_start,
        replay_end=replay_end,
        time_step_minutes=args.step_minutes,
        available_sources=available_sources,
        reference_sources=("JCYL_HISTORICAL_FIRES",),
        sensor_availability=sensor_availability,
        input_hashes=tuple(item.input_hash for item in unique_inputs),
        case_version="phase6-pilot-v1",
        selection_policy_version="historical-corpus-selection-v1",
        reference_quality=event.reference_quality.value,
    )

    database = VigiaDatabase(settings.SUPABASE_DB_URL.get_secret_value())
    try:
        corpus_result = await HistoricalCorpusRepository(database).persist(pilot)
        repository = ReplayRepository(database)
        await repository.persist_case(manifest, unique_inputs)
        clock = ReplayClock(
            start=replay_start,
            end=replay_end,
            step=timedelta(minutes=args.step_minutes),
        )
        engine = ReplayEngine(
            data_context=ReplayDataContext(unique_inputs),
            clock=clock,
            fusion_config=load_fusion_config(),
        )
        tracemalloc.start()
        started = datetime.now(UTC)
        monotonic = perf_counter()
        result = engine.run(manifest, code_commit=args.code_commit)
        elapsed_ms = round((perf_counter() - monotonic) * 1000)
        _, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        run_id = await repository.persist_run(
            result,
            configuration=load_fusion_config().model_dump(mode="json"),
            started_at=started,
            elapsed_ms=elapsed_ms,
            approximate_peak_memory_bytes=peak_memory,
        )
    finally:
        await database.close()
    states = sorted(
        {
            incident.state
            for step in result.steps
            for incident in step.incidents
        }
    )
    print(
        json.dumps(
            {
                "event": "phase6_pilot_completed",
                "historical_event": event.vigia_code,
                "case_id": case_id,
                "run_id": str(run_id),
                "pilot_events": corpus_result.events,
                "references_written": corpus_result.references,
                "replay_start": replay_start.isoformat(),
                "replay_end": replay_end.isoformat(),
                "steps": len(result.steps),
                "historical_inputs": len(unique_inputs),
                "observations_processed": result.observations_processed,
                "states_observed": states,
                "risk_availability": sorted({step.risk["availability"] for step in result.steps}),
                "aemet_daily_records": aemet_records,
                "elapsed_ms": elapsed_ms,
                "approximate_peak_memory_bytes": peak_memory,
                "live_state_mutated": result.live_state_mutated,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(run())
