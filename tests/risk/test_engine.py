from datetime import UTC, datetime, timedelta

import pytest

from vigia_ai.risk.engine import RiskEngine
from vigia_ai.risk.models import ComponentEvidence, RiskDataQuality, RiskMode
from vigia_ai.risk.weather import StationValue, interpolate_idw

NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)


def _component(name: str, score: float | None, observed_at: datetime = NOW) -> ComponentEvidence:
    return ComponentEvidence(
        name=name,
        score=score,
        observed_at=observed_at,
        source="TEST_FIXTURE",
        resolution_m=1000.0,
        quality=RiskDataQuality.COMPLETE if score is not None else RiskDataQuality.INSUFFICIENT,
    )


def test_engine_is_deterministic_and_not_probability() -> None:
    components = (_component("fire_weather", 60.0), _component("vegetation", 30.0))
    first = RiskEngine().assess(components, as_of=NOW, valid_at=NOW, mode=RiskMode.ANALYSIS)
    second = RiskEngine().assess(components, as_of=NOW, valid_at=NOW, mode=RiskMode.ANALYSIS)
    assert first == second
    assert first.experimental_index == 45.0
    assert first.risk_class == "MODERADO"
    assert "no es una probabilidad" in first.disclaimer


def test_engine_refuses_future_leakage() -> None:
    with pytest.raises(ValueError, match="future leakage"):
        RiskEngine().assess(
            (
                _component("fire_weather", 60.0, NOW + timedelta(seconds=1)),
                _component("terrain", 20.0),
            ),
            as_of=NOW,
            valid_at=NOW,
            mode=RiskMode.ANALYSIS,
        )


def test_engine_reports_missing_critical_component() -> None:
    result = RiskEngine().assess(
        (_component("fire_weather", None), _component("terrain", 20.0)),
        as_of=NOW,
        valid_at=NOW,
        mode=RiskMode.ANALYSIS,
    )
    assert result.experimental_index is None
    assert result.risk_class == "NO_DISPONIBLE"
    assert result.data_quality is RiskDataQuality.INSUFFICIENT
    assert "INSUFFICIENT_COMPONENTS_FOR_COMPOSITE" in result.reason_codes


def test_idw_filters_future_stale_forecast_and_distant_samples() -> None:
    samples = (
        StationValue("A", 40.0, -4.0, NOW - timedelta(hours=1), 20.0),
        StationValue("B", 40.1, -4.0, NOW - timedelta(hours=2), 30.0),
        StationValue("FUTURE", 40.0, -4.0, NOW + timedelta(minutes=1), 99.0),
        StationValue("FORECAST", 40.0, -4.0, NOW, 99.0, "PRONOSTICADO"),
        StationValue("STALE", 40.0, -4.0, NOW - timedelta(days=2), 99.0),
        StationValue("FAR", 42.0, -4.0, NOW, 99.0),
    )
    result = interpolate_idw(
        samples,
        latitude=40.05,
        longitude=-4.0,
        as_of=NOW,
        max_age=timedelta(hours=6),
        max_distance_km=50.0,
    )
    assert result.value == pytest.approx(25.0, abs=0.01)
    assert set(result.stations) == {"A", "B"}
    assert result.method == "IDW_P2"
