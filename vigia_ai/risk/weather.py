from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast


@dataclass(frozen=True, slots=True)
class StationValue:
    station_code: str
    latitude: float
    longitude: float
    observed_at: datetime
    value: float | None
    value_type: str = "OBSERVADO"


@dataclass(frozen=True, slots=True)
class InterpolatedValue:
    value: float | None
    method: str
    stations: tuple[str, ...]
    distances_km: tuple[float, ...]
    effective_resolution_m: float | None
    observed_at: datetime | None
    reason_codes: tuple[str, ...]


def haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    radius_km = 6371.0088
    lat1, lat2 = math.radians(lat_a), math.radians(lat_b)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(lon_b - lon_a)
    value = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
    )
    return radius_km * 2.0 * math.atan2(math.sqrt(value), math.sqrt(1.0 - value))


def interpolate_idw(
    samples: tuple[StationValue, ...],
    *,
    latitude: float,
    longitude: float,
    as_of: datetime,
    max_age: timedelta,
    max_distance_km: float,
    max_stations: int = 6,
    power: float = 2.0,
) -> InterpolatedValue:
    if power <= 0.0 or max_stations < 1 or max_distance_km <= 0.0:
        raise ValueError("Configuración IDW no válida")
    eligible: list[tuple[float, StationValue]] = []
    for sample in samples:
        if sample.value is None or sample.value_type != "OBSERVADO":
            continue
        if sample.observed_at > as_of or as_of - sample.observed_at > max_age:
            continue
        distance = haversine_km(latitude, longitude, sample.latitude, sample.longitude)
        if distance <= max_distance_km:
            eligible.append((distance, sample))
    eligible.sort(key=lambda item: (item[0], item[1].station_code))
    selected = eligible[:max_stations]
    if not selected:
        return InterpolatedValue(
            value=None,
            method="IDW_P2",
            stations=(),
            distances_km=(),
            effective_resolution_m=None,
            observed_at=None,
            reason_codes=("NO_ELIGIBLE_WEATHER_STATIONS",),
        )
    exact = next(((distance, sample) for distance, sample in selected if distance < 1e-9), None)
    if exact is not None:
        chosen = exact[1]
        return InterpolatedValue(
            value=chosen.value,
            method="STATION_EXACT",
            stations=(chosen.station_code,),
            distances_km=(0.0,),
            effective_resolution_m=0.0,
            observed_at=chosen.observed_at,
            reason_codes=(),
        )
    weights = [distance**-power for distance, _ in selected]
    value = sum(
        weight * cast(float, sample.value)
        for weight, (_, sample) in zip(weights, selected, strict=True)
    ) / sum(weights)
    distances = tuple(distance for distance, _ in selected)
    return InterpolatedValue(
        value=value,
        method=f"IDW_P{power:g}",
        stations=tuple(sample.station_code for _, sample in selected),
        distances_km=distances,
        effective_resolution_m=max(distances) * 2000.0,
        observed_at=max(sample.observed_at for _, sample in selected),
        reason_codes=("SINGLE_STATION_CONTEXT",) if len(selected) == 1 else (),
    )
