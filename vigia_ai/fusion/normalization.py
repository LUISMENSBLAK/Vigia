from datetime import datetime
from typing import Any

from .config import FusionConfig
from .models import ObservationEvidence, SourceFamily


def source_family(source_code: str, sensor: str, platform: str) -> SourceFamily:
    normalized = f"{source_code} {sensor} {platform}".upper()
    if "NASA_FIRMS" in normalized and "VIIRS" in normalized:
        return SourceFamily.NASA_VIIRS
    if "NASA_FIRMS" in normalized and "MODIS" in normalized:
        return SourceFamily.NASA_MODIS
    if "EUMETSAT" in normalized or "MTG" in normalized:
        return SourceFamily.EUMETSAT_MTG
    if "SENTINEL_1" in normalized or "RADAR" in normalized:
        return SourceFamily.COPERNICUS_RADAR
    if "SENTINEL_2" in normalized or "OPTICAL" in normalized:
        return SourceFamily.COPERNICUS_OPTICAL
    if "SENTINEL_3" in normalized or "SLSTR" in normalized:
        return SourceFamily.COPERNICUS_THERMAL
    if "AEMET" in normalized:
        return SourceFamily.AEMET_WEATHER
    return SourceFamily.UNKNOWN


def normalize_database_row(
    row: dict[str, Any], *, config: FusionConfig, as_of: datetime
) -> ObservationEvidence:
    family = source_family(str(row["source_code"]), str(row["sensor"]), str(row["platform"]))
    profile = config.source_profiles[family]
    observed_at = row["observed_at"]
    quality = dict(row.get("quality") or {})
    if row.get("known_heat_source_match") is True:
        quality["known_heat_source_match"] = True
    return ObservationEvidence(
        observation_id=str(row["id"]),
        source=str(row["source_name"]),
        provider=str(row["provider"]),
        platform=str(row["platform"]),
        sensor=str(row["sensor"]),
        observed_at=observed_at,
        received_at=row["received_at"],
        processed_at=None,
        longitude=float(row["longitude"]),
        latitude=float(row["latitude"]),
        spatial_resolution_m=float(row.get("spatial_resolution_m") or profile.spatial_resolution_m),
        temporal_age_seconds=max(0, int((as_of - observed_at).total_seconds())),
        confidence_raw=row.get("confidence_raw"),
        fire_probability=row.get("fire_probability"),
        frp_mw=row.get("frp_mw"),
        brightness_kelvin=row.get("brightness_kelvin"),
        daynight=row.get("daynight"),
        quality=quality,
        provenance=row.get("provenance"),
        source_family=family,
    )
