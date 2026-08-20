from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from vigia_ai.risk.fwi import calculate_fwi_sequence
from vigia_ai.risk.models import FWIResult, FWIState, FWIWeather


class FWIInitializationMethod(StrEnum):
    HISTORICAL_WARMUP = "HISTORICAL_WARMUP"
    STANDARD_SNOW_STARTUP = "STANDARD_SNOW_STARTUP"


class StoredFWIState(BaseModel):
    station_code: str
    observed_at: datetime
    state: FWIState
    method: FWIInitializationMethod
    source: str
    quality_flags: tuple[str, ...] = ()


class FWIStateStore:
    def __init__(self) -> None:
        self._states: dict[str, list[StoredFWIState]] = {}

    def put(self, item: StoredFWIState) -> None:
        if item.observed_at.tzinfo is None:
            raise ValueError("El estado FWI requiere zona horaria")
        states = self._states.setdefault(item.station_code, [])
        states[:] = [state for state in states if state.observed_at != item.observed_at]
        states.append(item)
        states.sort(key=lambda state: state.observed_at)

    def latest(self, station_code: str, *, as_of: datetime) -> StoredFWIState | None:
        if as_of.tzinfo is None:
            raise ValueError("as_of requiere zona horaria")
        eligible = [
            state for state in self._states.get(station_code, []) if state.observed_at <= as_of
        ]
        return eligible[-1] if eligible else None

    def warm_up(
        self,
        station_code: str,
        weather_days: tuple[FWIWeather, ...],
        *,
        initial: StoredFWIState,
        minimum_days: int,
    ) -> tuple[FWIResult, ...]:
        if initial.station_code != station_code:
            raise ValueError("El estado inicial pertenece a otra estación")
        if len(weather_days) < minimum_days:
            return ()
        if weather_days and weather_days[0].observed_at <= initial.observed_at:
            raise ValueError("El warm-up no puede utilizar tiempo anterior al estado inicial")
        results = calculate_fwi_sequence(weather_days, initial_state=initial.state)
        for result in results:
            self.put(
                StoredFWIState(
                    station_code=station_code,
                    observed_at=result.observed_at,
                    state=result.state,
                    method=FWIInitializationMethod.HISTORICAL_WARMUP,
                    source=initial.source,
                    quality_flags=initial.quality_flags,
                )
            )
        return results


def documented_snow_startup(
    station_code: str, *, observed_at: datetime, source: str
) -> StoredFWIState:
    """NRCan documented seasonal start; explicit estimate, never an observation."""
    return StoredFWIState(
        station_code=station_code,
        observed_at=observed_at,
        state=FWIState(ffmc=85.0, dmc=6.0, dc=15.0),
        method=FWIInitializationMethod.STANDARD_SNOW_STARTUP,
        source=source,
        quality_flags=("INITIALIZED_NOT_OBSERVED", "REQUIRES_SNOW_STARTUP_CRITERIA"),
    )
