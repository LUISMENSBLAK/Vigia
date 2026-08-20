from datetime import UTC, datetime

import pytest

from vigia_ai.risk.fwi import calculate_fwi_day, calculate_fwi_sequence
from vigia_ai.risk.models import FWIState, FWIWeather


def _weather(month: int, day: int, temp: float, rh: float, wind: float, rain: float) -> FWIWeather:
    return FWIWeather(
        observed_at=datetime(2026, month, day, 12, tzinfo=UTC),
        temperature_c=temp,
        relative_humidity_pct=rh,
        wind_speed_kmh=wind,
        precipitation_24h_mm=rain,
    )


def test_matches_nrcan_nor_x_424_published_sequence() -> None:
    # Table 7, Wang, Anderson & Suddaby (2015), starting FFMC=85, DMC=6, DC=15.
    weather = (
        _weather(4, 13, 17.0, 42.0, 25.0, 0.0),
        _weather(4, 14, 20.0, 21.0, 25.0, 2.4),
        _weather(4, 15, 8.5, 40.0, 17.0, 0.0),
        _weather(4, 16, 6.5, 25.0, 6.0, 0.0),
        _weather(4, 17, 13.0, 34.0, 24.0, 0.0),
    )
    expected = (
        (87.7, 8.5, 19.0, 10.9, 8.5, 10.1),
        (86.2, 10.4, 23.6, 8.8, 10.4, 9.3),
        (87.0, 11.8, 26.1, 6.5, 11.7, 7.6),
        (88.8, 13.2, 28.2, 4.9, 13.1, 6.2),
        (89.1, 15.4, 31.5, 12.6, 15.3, 14.8),
    )
    results = calculate_fwi_sequence(weather, initial_state=FWIState(85.0, 6.0, 15.0))
    for result, values in zip(results, expected, strict=True):
        assert (
            result.ffmc,
            result.dmc,
            result.dc,
            result.isi,
            result.bui,
            result.fwi,
        ) == pytest.approx(values, abs=0.06)


def test_requires_explicit_valid_previous_state() -> None:
    with pytest.raises(ValueError, match="estado FWI"):
        calculate_fwi_day(_weather(4, 13, 17.0, 42.0, 25.0, 0.0), FWIState(102.0, 6.0, 15.0))


def test_rejects_non_chronological_sequence() -> None:
    day = _weather(4, 13, 17.0, 42.0, 25.0, 0.0)
    with pytest.raises(ValueError, match="estrictamente ordenada"):
        calculate_fwi_sequence((day, day), initial_state=FWIState(85.0, 6.0, 15.0))
