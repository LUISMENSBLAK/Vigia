import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vigia_ai.detection.engine import recommend_state
from vigia_ai.detection.models import IncidentState, ReasonCode
from vigia_ai.detection.state_machine import transition_path
from vigia_ai.fusion.config import load_fusion_config
from vigia_ai.fusion.engine import fuse_observations
from vigia_ai.fusion.geodesy import geodesic_distance_m
from vigia_ai.fusion.models import EvidenceRole, ObservationEvidence, SourceFamily
from vigia_ai.fusion.normalization import source_family
from vigia_ai.fusion.repository import incident_code

FIXTURE = Path("tests/fixtures/fusion_observations.json")


def synthetic_observations() -> list[ObservationEvidence]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["notice"].startswith("SYNTHETIC TEST DATA")
    return [ObservationEvidence.model_validate(item) for item in payload["observations"]]


def test_geodesic_distance_uses_metres_not_degrees() -> None:
    distance = geodesic_distance_m((0, 0), (0, 1))
    assert 111_000 < distance < 112_000


def test_viirs_platforms_share_one_approximate_independence_family() -> None:
    families = {
        source_family("NASA_FIRMS_VIIRS_NOAA20_NRT", "VIIRS", "N20"),
        source_family("NASA_FIRMS_VIIRS_NOAA21_NRT", "VIIRS", "N21"),
        source_family("NASA_FIRMS_VIIRS_SNPP_NRT", "VIIRS", "SNPP"),
    }
    assert families == {SourceFamily.NASA_VIIRS}


def test_as_of_excludes_future_observations_without_leakage() -> None:
    config = load_fusion_config()
    result = fuse_observations(
        synthetic_observations(),
        config=config,
        as_of=datetime(2026, 8, 20, 12, 40, tzinfo=UTC),
    )
    assert result.input_observation_count == 5
    assert result.eligible_observation_count == 4
    assert result.candidate_count == 1
    assert all(
        item.observation.observed_at <= result.as_of
        for candidate in result.candidates
        for item in candidate.observations
    )


def test_as_of_excludes_observation_received_after_cutoff() -> None:
    config = load_fusion_config()
    observation = synthetic_observations()[0].model_copy(
        update={"received_at": datetime(2026, 8, 20, 12, 45, tzinfo=UTC)}
    )
    result = fuse_observations(
        [observation],
        config=config,
        as_of=datetime(2026, 8, 20, 12, 40, tzinfo=UTC),
    )
    assert result.eligible_observation_count == 0
    assert result.candidate_count == 0


def test_clustering_is_deterministic_and_idempotent() -> None:
    config = load_fusion_config()
    observations = synthetic_observations()[:4]
    as_of = datetime(2026, 8, 20, 12, 40, tzinfo=UTC)
    first = fuse_observations(observations, config=config, as_of=as_of)
    second = fuse_observations(list(reversed(observations)), config=config, as_of=as_of)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.candidates[0].candidate_id == second.candidates[0].candidate_id
    assert incident_code(first.candidates[0]) == incident_code(second.candidates[0])


def test_incident_identity_survives_later_evidence() -> None:
    config = load_fusion_config()
    observations = synthetic_observations()[:4]
    as_of = datetime(2026, 8, 20, 12, 40, tzinfo=UTC)
    initial = fuse_observations(observations[:2], config=config, as_of=as_of)
    extended = fuse_observations(observations, config=config, as_of=as_of)
    assert incident_code(initial.candidates[0]) == incident_code(extended.candidates[0])


def test_temporal_persistence_and_multi_family_detection_are_explicit() -> None:
    config = load_fusion_config()
    as_of = datetime(2026, 8, 20, 12, 40, tzinfo=UTC)
    candidate = fuse_observations(
        synthetic_observations()[:4], config=config, as_of=as_of
    ).candidates[0]
    recommendation = recommend_state(candidate, config=config, as_of=as_of)
    assert candidate.persistence.detection_count == 4
    assert candidate.persistence.persistence_seconds == 1800
    assert set(candidate.source_families) == {
        SourceFamily.NASA_VIIRS,
        SourceFamily.NASA_MODIS,
    }
    assert recommendation.recommended_state is IncidentState.PROBABLE_INCENDIO
    assert ReasonCode.MULTI_FAMILY_AGREEMENT in recommendation.reason_codes
    assert recommendation.calibrated_probability is None


def test_spatially_distant_observation_creates_separate_candidate() -> None:
    config = load_fusion_config()
    observations = synthetic_observations()[:2]
    distant = observations[1].model_copy(
        update={"observation_id": "synthetic-distant", "longitude": 1.0, "latitude": 1.0}
    )
    result = fuse_observations(
        [observations[0], distant],
        config=config,
        as_of=datetime(2026, 8, 20, 12, 40, tzinfo=UTC),
    )
    assert result.candidate_count == 2


def test_known_heat_source_is_contradicting_not_confirming() -> None:
    config = load_fusion_config()
    observation = synthetic_observations()[0].model_copy(
        update={"quality": {"synthetic_test_data": True, "known_heat_source_match": True}}
    )
    as_of = datetime(2026, 8, 20, 12, 10, tzinfo=UTC)
    candidate = fuse_observations([observation], config=config, as_of=as_of).candidates[0]
    assert candidate.observations[0].role is EvidenceRole.CONTRADICTING
    recommendation = recommend_state(candidate, config=config, as_of=as_of)
    assert recommendation.recommended_state is IncidentState.DESCARTADO
    assert ReasonCode.KNOWN_HEAT_SOURCE in recommendation.reason_codes


def test_expired_candidate_is_stale_and_cannot_escalate() -> None:
    config = load_fusion_config()
    as_of = datetime(2026, 8, 20, 15, 31, tzinfo=UTC)
    candidate = fuse_observations(
        synthetic_observations()[:4], config=config, as_of=as_of
    ).candidates[0]
    recommendation = recommend_state(candidate, config=config, as_of=as_of)
    assert recommendation.recommended_state is IncidentState.VIGILANCIA
    assert ReasonCode.STALE_DATA in recommendation.reason_codes


def test_state_machine_rejects_automatic_confirmation() -> None:
    with pytest.raises(ValueError, match="confirmación externa"):
        transition_path(IncidentState.SIN_EVIDENCIA, IncidentState.INCENDIO_CONFIRMADO)
    assert transition_path(IncidentState.SIN_EVIDENCIA, IncidentState.POSIBLE_IGNICION) == (
        IncidentState.VIGILANCIA,
        IncidentState.ANOMALIA,
        IncidentState.POSIBLE_IGNICION,
    )
    assert transition_path(IncidentState.PROBABLE_INCENDIO, IncidentState.VIGILANCIA) == (
        IncidentState.POSIBLE_IGNICION,
        IncidentState.ANOMALIA,
        IncidentState.VIGILANCIA,
    )
