from datetime import UTC, datetime

from vigia_ai.confidence.contracts import (
    REQUIRED_CONFIDENCE_DIMENSIONS,
    EvidenceDescriptor,
    ResearchConfidenceAssessment,
)


def test_research_contract_cannot_emit_probability() -> None:
    evidence = EvidenceDescriptor(
        observation_id="test-observation",
        source="NASA FIRMS",
        platform="N20",
        sensor="VIIRS",
        independence_group="viirs-noaa20",
        observed_at=datetime(2026, 8, 16, tzinfo=UTC),
        age_seconds=120,
        resolution_m=375,
        persistence_count=1,
        confidence_raw="n",
        input_hash="a" * 64,
    )
    assessment = ResearchConfidenceAssessment(
        engine_version="research-contract-v1",
        evidence=[evidence],
        spatial_consistency_evaluated=False,
        temporal_consistency_evaluated=False,
        meteorology_evaluated=False,
        vegetation_evaluated=False,
        contradictions_evaluated=False,
    )
    assert assessment.status == "research"
    assert assessment.calibrated_probability is None
    assert "independence" in REQUIRED_CONFIDENCE_DIMENSIONS
    assert "contradictions" in REQUIRED_CONFIDENCE_DIMENSIONS
