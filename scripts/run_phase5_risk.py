from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from services.api.vigia_api.config import get_settings
from services.api.vigia_api.database import VigiaDatabase
from vigia_ai.risk.engine import (
    RiskEngine,
    normalized_ndmi_dryness,
    normalized_slope_context,
)
from vigia_ai.risk.models import ComponentEvidence, RiskDataQuality, RiskMode
from vigia_ai.risk.repository import RiskRepository
from vigia_ai.risk.weather import InterpolatedValue, StationValue, interpolate_idw
from vigia_geospatial.materialize import (
    load_materialization_config,
    resolved_aoi,
)
from vigia_geospatial.serving import sample_raster

RISK_CONFIGURATION = json.loads(
    Path("config/risk/risk-baseline-v1.json").read_text(encoding="utf-8")
)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("as_of requiere zona horaria")
    return parsed.astimezone(UTC)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta Risk baseline para una AOI configurada")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--as-of", type=parse_time, default=datetime.now(UTC))
    parser.add_argument("--code-commit", required=True)
    return parser.parse_args()


def estimate(
    rows: list[dict[str, Any]],
    field: str,
    *,
    latitude: float,
    longitude: float,
    as_of: datetime,
    scale: float = 1.0,
) -> InterpolatedValue:
    samples = tuple(
        StationValue(
            station_code=str(row["station_code"]),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            observed_at=row["observed_at"],
            value=None if row[field] is None else float(row[field]) * scale,
        )
        for row in rows
    )
    return interpolate_idw(
        samples,
        latitude=latitude,
        longitude=longitude,
        as_of=as_of,
        max_age=timedelta(hours=6),
        max_distance_km=100,
    )


async def run() -> None:
    args = arguments()
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        raise SystemExit("NO DISPONIBLE: falta SUPABASE_DB_URL")
    database = VigiaDatabase(settings.SUPABASE_DB_URL.get_secret_value())
    repository = RiskRepository(database)
    aoi = resolved_aoi(load_materialization_config(args.config))
    longitude, latitude = aoi.geometry.centroid.x, aoi.geometry.centroid.y
    started_at = datetime.now(UTC)
    try:
        weather_rows = await repository.observed_weather_stations(
            longitude=longitude,
            latitude=latitude,
            as_of=args.as_of,
            max_age=timedelta(hours=6),
            max_distance_km=100,
        )
        temperature = estimate(
            weather_rows,
            "temperature_c",
            latitude=latitude,
            longitude=longitude,
            as_of=args.as_of,
        )
        humidity = estimate(
            weather_rows,
            "relative_humidity_pct",
            latitude=latitude,
            longitude=longitude,
            as_of=args.as_of,
        )
        wind = estimate(
            weather_rows,
            "wind_speed_ms",
            latitude=latitude,
            longitude=longitude,
            as_of=args.as_of,
            scale=3.6,
        )
        precipitation = estimate(
            weather_rows,
            "precipitation_mm",
            latitude=latitude,
            longitude=longitude,
            as_of=args.as_of,
        )
        product_rows = await database.geospatial_context(
            longitude=longitude, latitude=latitude, as_of=args.as_of
        )
        products = {str(row["layer"]): row for row in product_rows}

        def raster_value(layer: str) -> float | None:
            row = products.get(layer)
            if row is None or not row.get("storage_uri") or not row.get("raster_band"):
                return None
            return sample_raster(
                str(row["storage_uri"]),
                longitude=longitude,
                latitude=latitude,
                band=int(row["raster_band"]),
                storage_root=Path(settings.GEOSPATIAL_STORAGE_ROOT),
            )

        ndmi = raster_value("NDMI")
        slope = raster_value("SLOPE")
        weather_time = max(
            (
                value.observed_at
                for value in (temperature, humidity, wind, precipitation)
                if value.observed_at is not None
            ),
            default=None,
        )
        components = (
            ComponentEvidence(
                "fire_weather",
                None,
                weather_time,
                "AEMET OpenData",
                max(
                    (
                        value.effective_resolution_m or 0.0
                        for value in (temperature, humidity, wind, precipitation)
                    ),
                    default=None,
                ),
                RiskDataQuality.INSUFFICIENT,
                ("FWI_PREVIOUS_STATE_UNAVAILABLE",),
                {
                    "temperature_c": temperature.value,
                    "relative_humidity_pct": humidity.value,
                    "wind_speed_kmh": wind.value,
                    "precipitation_mm_observation": precipitation.value,
                    "method": temperature.method,
                    "stations": sorted(
                        set(
                            temperature.stations
                            + humidity.stations
                            + wind.stations
                            + precipitation.stations
                        )
                    ),
                },
            ),
            ComponentEvidence(
                "vegetation",
                normalized_ndmi_dryness(float(ndmi)) if ndmi is not None else None,
                products.get("NDMI", {}).get("observed_at"),
                "Copernicus Sentinel-2",
                products.get("NDMI", {}).get("output_resolution_m"),
                RiskDataQuality.COMPLETE if ndmi is not None else RiskDataQuality.INSUFFICIENT,
                () if ndmi is not None else ("NDMI_UNAVAILABLE",),
                {"ndmi": ndmi, "product_id": products.get("NDMI", {}).get("product_id")},
            ),
            ComponentEvidence(
                "terrain",
                normalized_slope_context(float(slope)) if slope is not None else None,
                None,
                "IGN MDT05",
                products.get("SLOPE", {}).get("output_resolution_m"),
                RiskDataQuality.COMPLETE if slope is not None else RiskDataQuality.INSUFFICIENT,
                () if slope is not None else ("SLOPE_UNAVAILABLE",),
                {"slope_deg": slope, "product_id": products.get("SLOPE", {}).get("product_id")},
            ),
        )
        assessment = RiskEngine().assess(
            components,
            as_of=args.as_of,
            valid_at=args.as_of,
            mode=RiskMode.ANALYSIS,
        )
        configuration = RISK_CONFIGURATION
        snapshot = {
            "weather_station_codes": sorted({str(row["station_code"]) for row in weather_rows}),
            "geospatial_product_ids": [
                row["product_id"]
                for layer in ("NDMI", "SLOPE")
                if (row := products.get(layer)) is not None
            ],
            "as_of": args.as_of.isoformat(),
            "fwi_previous_state": None,
        }
        prediction_id = await repository.persist_assessment(
            assessment,
            aoi_geojson=aoi.geojson,
            longitude=longitude,
            latitude=latitude,
            configuration=configuration,
            input_snapshot=snapshot,
            software_version="vigia/0.5.0",
            code_commit=args.code_commit,
            request_id=str(uuid4()),
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        print(
            json.dumps(
                {
                    "event": "risk_run_completed",
                    "prediction_id": str(prediction_id),
                    "aoi_id": aoi.reference,
                    "as_of": args.as_of.isoformat(),
                    "data_quality": assessment.data_quality,
                    "experimental_index": assessment.experimental_index,
                    "risk_class": assessment.risk_class,
                    "weather_stations": len(weather_rows),
                    "ndmi_available": ndmi is not None,
                    "slope_available": slope is not None,
                    "reason_codes": assessment.reason_codes,
                },
                sort_keys=True,
            )
        )
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(run())
