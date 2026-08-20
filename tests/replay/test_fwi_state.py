from datetime import UTC, datetime, timedelta

from vigia_ai.replay.fwi_state import (
    FWIInitializationMethod,
    FWIStateStore,
    documented_snow_startup,
)
from vigia_ai.risk.models import FWIWeather

START = datetime(2025, 5, 1, 12, tzinfo=UTC)


def weather(day: int, rain: float = 0.0) -> FWIWeather:
    return FWIWeather(
        observed_at=START + timedelta(days=day),
        temperature_c=20,
        relative_humidity_pct=40,
        wind_speed_kmh=15,
        precipitation_24h_mm=rain,
    )


def test_fwi_warmup_continuity_and_precipitation() -> None:
    store = FWIStateStore()
    initial = documented_snow_startup("A", observed_at=START, source="NRCan startup")
    store.put(initial)
    results = store.warm_up(
        "A", (weather(1), weather(2, rain=10), weather(3)), initial=initial, minimum_days=3
    )
    assert len(results) == 3
    assert store.latest("A", as_of=START + timedelta(days=2)) is not None
    latest = store.latest("A", as_of=START + timedelta(days=3))
    assert latest is not None
    assert latest.method is FWIInitializationMethod.HISTORICAL_WARMUP
    assert results[1].ffmc < results[0].ffmc


def test_fwi_store_never_reads_future_state() -> None:
    store = FWIStateStore()
    initial = documented_snow_startup("A", observed_at=START, source="NRCan startup")
    store.put(initial)
    store.warm_up("A", (weather(1),), initial=initial, minimum_days=1)
    assert store.latest("A", as_of=START) == initial
    assert store.latest("A", as_of=START - timedelta(seconds=1)) is None


def test_insufficient_warmup_returns_no_state() -> None:
    store = FWIStateStore()
    initial = documented_snow_startup("A", observed_at=START, source="NRCan startup")
    assert store.warm_up("A", (weather(1),), initial=initial, minimum_days=7) == ()
    assert "INITIALIZED_NOT_OBSERVED" in initial.quality_flags
