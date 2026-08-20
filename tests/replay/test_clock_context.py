from datetime import UTC, datetime, timedelta

import pytest

from vigia_ai.replay.clock import ReplayClock
from vigia_ai.replay.context import ReplayDataContext
from vigia_ai.replay.models import ReplayInput, ReplayInputKind

START = datetime(2025, 8, 16, 12, tzinfo=UTC)


def item(
    observed_at: datetime, *, available_at: datetime | None = None, suffix: str = ""
) -> ReplayInput:
    return ReplayInput(
        input_id=observed_at.isoformat() + suffix,
        kind=ReplayInputKind.SENTINEL_PRODUCT,
        source="COPERNICUS_SENTINEL_2",
        observed_at=observed_at,
        available_at=available_at or observed_at,
        payload={"product_id": "S2"},
        provenance={"provider": "Copernicus"},
        availability_basis="PUBLISHED",
    )


def test_replay_clock_is_explicit_and_bounded() -> None:
    clock = ReplayClock(start=START, end=START + timedelta(minutes=20), step=timedelta(minutes=10))
    assert clock.timeline() == (START, START + timedelta(minutes=10), START + timedelta(minutes=20))
    with pytest.raises(ValueError):
        clock.seek(START + timedelta(hours=1))


def test_future_observation_and_future_availability_are_excluded() -> None:
    context = ReplayDataContext(
        (
            item(START, suffix="-visible"),
            item(START, available_at=START + timedelta(minutes=20), suffix="-delayed"),
            item(START + timedelta(minutes=10)),
        )
    )
    explanations = context.explain(as_of=START)
    assert [entry.included for entry in explanations].count(True) == 1
    assert {entry.reason for entry in explanations if not entry.included} == {
        "FUTURE_OBSERVATION",
        "NOT_YET_AVAILABLE",
    }


def test_truth_fields_are_rejected_at_firewall() -> None:
    with pytest.raises(ValueError, match="TRUTH_FIREWALL"):
        ReplayInput(
            input_id="truth",
            kind=ReplayInputKind.TERRAIN_PRODUCT,
            source="REFERENCE",
            observed_at=START,
            available_at=START,
            payload={"final_perimeter": {}},
            provenance={},
            availability_basis="PUBLISHED",
        )


def test_future_perimeter_cannot_cross_truth_firewall_even_when_nested() -> None:
    with pytest.raises(ValueError, match="TRUTH_FIREWALL"):
        ReplayInput(
            input_id="future-perimeter",
            kind=ReplayInputKind.SENTINEL_PRODUCT,
            source="GROUND_TRUTH",
            observed_at=START + timedelta(days=2),
            available_at=START + timedelta(days=2),
            payload={"metadata": {"reference_perimeter": {"type": "Polygon"}}},
            provenance={},
            availability_basis="PUBLISHED",
        )


def test_future_weather_uses_the_same_temporal_gate() -> None:
    weather = ReplayInput(
        input_id="future-weather",
        kind=ReplayInputKind.WEATHER_OBSERVATION,
        source="AEMET_HISTORICAL",
        observed_at=START + timedelta(hours=1),
        available_at=START + timedelta(hours=2),
        payload={"temperature_c": 20.0},
        provenance={"station": "official-station"},
        availability_basis="PUBLISHED",
    )
    explanation = ReplayDataContext((weather,)).explain(as_of=START)[0]
    assert explanation.included is False
    assert explanation.reason == "FUTURE_OBSERVATION"
