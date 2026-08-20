from datetime import UTC, datetime, timedelta
from pathlib import Path

from vigia_ai.fusion.config import load_fusion_config
from vigia_ai.replay.clock import ReplayClock
from vigia_ai.replay.context import ReplayDataContext
from vigia_ai.replay.engine import ReplayEngine
from vigia_ai.replay.models import ReplayCaseManifest, ReplayInput, ReplayInputKind

START = datetime(2025, 8, 16, 13, 50, tzinfo=UTC)


def thermal(index: int, minute: int) -> ReplayInput:
    observed = START + timedelta(minutes=minute)
    return ReplayInput(
        input_id=f"thermal-{index}",
        kind=ReplayInputKind.THERMAL_OBSERVATION,
        source="NASA_FIRMS_VIIRS_NOAA20_SP",
        observed_at=observed,
        available_at=observed,
        longitude=-5.035 + index * 0.0001,
        latitude=42.658 + index * 0.0001,
        availability_basis="OBSERVATION_TIME_PROXY",
        quality_flags=("HISTORICAL_AVAILABILITY_PROXY",),
        provenance={"dataset": "VIIRS standard processing", "input_hash": str(index)},
        payload={
            "provider": "NASA LANCE FIRMS",
            "platform": "NOAA-20",
            "sensor": "VIIRS",
            "spatial_resolution_m": 375,
            "confidence_raw": "n",
            "frp_mw": 10 + index,
            "brightness_kelvin": 330,
            "daynight": "D",
            "source_family": "NASA_VIIRS",
        },
    )


def manifest(inputs: tuple[ReplayInput, ...]) -> ReplayCaseManifest:
    return ReplayCaseManifest(
        case_id="case-1",
        historical_fire_event_id="event-reference-only",
        case_kind="POSITIVE_REFERENCE",
        aoi_geojson={
            "type": "MultiPolygon",
            "coordinates": [
                [[[-5.2, 42.5], [-4.8, 42.5], [-4.8, 42.8], [-5.2, 42.8], [-5.2, 42.5]]]
            ],
        },
        replay_start=START,
        replay_end=START + timedelta(minutes=30),
        time_step_minutes=10,
        available_sources=("NASA_FIRMS_VIIRS_NOAA20_SP",),
        reference_sources=("Junta de Castilla y León",),
        sensor_availability={"VIIRS_NOAA20_SP": "AVAILABLE"},
        input_hashes=tuple(item.input_hash for item in inputs),
        case_version="pilot-v1",
        selection_policy_version="historical-pilot-v1",
        reference_quality="HIGH",
    )


def run(inputs: tuple[ReplayInput, ...]):  # type: ignore[no-untyped-def]
    case = manifest(inputs)
    return ReplayEngine(
        data_context=ReplayDataContext(inputs),
        clock=ReplayClock(
            start=case.replay_start,
            end=case.replay_end,
            step=timedelta(minutes=case.time_step_minutes),
        ),
        fusion_config=load_fusion_config(Path("config/fusion.v1.json")),
    ).run(case, code_commit="test-commit")


def test_replay_is_deterministic_and_never_mutates_live() -> None:
    inputs = (thermal(1, 10), thermal(2, 20), thermal(3, 30))
    first = run(inputs)
    second = run(tuple(reversed(inputs)))
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.live_state_mutated is False
    assert first.steps[0].visible_observation_count == 0
    assert first.steps[-1].visible_observation_count == 3


def test_adversarial_truth_without_inputs_produces_no_evidence() -> None:
    result = run(())
    assert all(not step.incidents for step in result.steps)
    assert all(step.visible_observation_count == 0 for step in result.steps)
    assert all(step.risk["availability"] == "UNAVAILABLE" for step in result.steps)


def test_incendio_confirmado_remains_blocked() -> None:
    result = run((thermal(1, 0), thermal(2, 10), thermal(3, 20), thermal(4, 30)))
    assert all(
        incident.state != "INCENDIO_CONFIRMADO"
        for step in result.steps
        for incident in step.incidents
    )


def test_resume_from_checkpoint_matches_uninterrupted_run() -> None:
    inputs = (thermal(1, 0), thermal(2, 10), thermal(3, 20), thermal(4, 30))
    complete = run(inputs)
    case = manifest(inputs)
    resumed = ReplayEngine(
        data_context=ReplayDataContext(inputs),
        clock=ReplayClock(
            start=case.replay_start,
            end=case.replay_end,
            step=timedelta(minutes=case.time_step_minutes),
        ),
        fusion_config=load_fusion_config(Path("config/fusion.v1.json")),
    ).run(case, code_commit="test-commit", completed_steps=complete.steps[:2])
    assert resumed.model_dump(mode="json") == complete.model_dump(mode="json")
