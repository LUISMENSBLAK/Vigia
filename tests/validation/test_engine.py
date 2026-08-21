from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median

import pytest
from pydantic import ValidationError

from vigia_ai.historical.models import (
    HistoricalTimestamp,
    TimestampPrecision,
)
from vigia_ai.validation.alert_metrics import alert_precision, false_alert_burden
from vigia_ai.validation.bootstrap import group_bootstrap_interval
from vigia_ai.validation.datasets import (
    build_corpus_version,
    validate_control_candidates,
)
from vigia_ai.validation.eligibility import metric_eligibility
from vigia_ai.validation.event_metrics import event_detection_metrics, f1_metric
from vigia_ai.validation.latency import censored_latency_interval_seconds, latency_metrics
from vigia_ai.validation.localization import localization_metrics
from vigia_ai.validation.matching import match_events
from vigia_ai.validation.models import (
    ControlWindow,
    HistoricalCorpusVersion,
    MatcherConfiguration,
    MetricStatus,
    SourceSnapshot,
    SplitRole,
    ValidationCaseKind,
    ValidationEvent,
    ValidationIncident,
    ValidationSplitManifest,
)
from vigia_ai.validation.reports import build_validation_report
from vigia_ai.validation.splits import (
    assert_no_group_leakage,
    assign_event_groups,
    frozen_temporal_group_split,
    members_for_role,
)
from vigia_ai.validation.statistics import (
    all_success_sample_size,
    wilson_interval,
    zero_failure_lower_bound,
)
from vigia_ai.validation.stratification import fire_size_bin, stratified_recall
from vigia_ai.validation.test_protection import authorize_test_access

NOW = datetime(2024, 7, 1, 12, tzinfo=UTC)


def event(
    identifier: str,
    *,
    when: datetime = NOW,
    longitude: float = -4.7,
    latitude: float = 40.6,
    area_ha: float | None = 20,
) -> ValidationEvent:
    return ValidationEvent(
        event_id=identifier,
        event_group_id=identifier,
        kind=ValidationCaseKind.POSITIVE_REFERENCE,
        region="Castilla y León",
        provinces=("AVILA",),
        reference_time=when,
        temporal_precision="MINUTE",
        longitude=longitude,
        latitude=latitude,
        spatial_precision="APPROXIMATE_POINT",
        reference_quality="HIGH",
        reference_sources=("OFFICIAL TEST FIXTURE",),
        reference_hash="a" * 64,
        area_ha=area_ha,
    )


def incident(
    identifier: str,
    *,
    when: datetime = NOW + timedelta(hours=1),
    longitude: float = -4.7,
    latitude: float = 40.6,
    state: str = "PROBABLE_INCENDIO",
    coverage: bool = True,
) -> ValidationIncident:
    return ValidationIncident(
        incident_id=identifier,
        case_id="case",
        state=state,  # type: ignore[arg-type]
        centroid=(longitude, latitude),
        first_signal_at=when,
        last_signal_at=when + timedelta(minutes=10),
        source_families=("NASA_VIIRS",),
        reference_coverage_sufficient=coverage,
    )


def source() -> SourceSnapshot:
    return SourceSnapshot(
        source="OFFICIAL_TEST",
        dataset="Official fixture",
        source_uri="https://example.invalid/official",
        checksum_sha256="b" * 64,
        retrieved_at=NOW,
        raw_record_count=10,
        normalized_event_count=10,
        years_covered=(2024,),
        regions_covered=("Castilla y León",),
    )


def corpus(events: tuple[ValidationEvent, ...]) -> HistoricalCorpusVersion:
    grouped = assign_event_groups(events)
    return build_corpus_version(
        grouped,
        (),
        dataset_version="test-corpus-v1",
        created_at=NOW,
        sources=(source(),),
        selection_policy_version="fixture-v1",
        coverage_limitations=("TEST FIXTURE",),
    )


def matcher() -> MatcherConfiguration:
    return MatcherConfiguration(
        matcher_version="matcher-test-v1",
        maximum_distance_m=10_000,
        maximum_time_gap_seconds=24 * 3600,
    )


def test_real_manifests_are_frozen_hash_valid_and_regional() -> None:
    dataset = HistoricalCorpusVersion.model_validate_json(
        Path("config/validation/historical-corpus-v1.json").read_text(encoding="utf-8")
    )
    split = ValidationSplitManifest.model_validate_json(
        Path("config/validation/validation-split-v1.json").read_text(encoding="utf-8")
    )
    assert dataset.verify_hash() and split.verify_hash()
    assert len(dataset.events) == 5_866
    assert len(dataset.controls) == 0
    assert dataset.regions_covered == ("Castilla y León",)
    assert split.counts == {"DEVELOPMENT": 3520, "TEST": 1172, "VALIDATION": 1174}
    assert split.test_frozen is True
    assert_no_group_leakage(split)


def test_grouping_and_split_are_deterministic_without_group_leakage() -> None:
    events = tuple(
        event(
            f"event-{index}",
            when=NOW + timedelta(days=index),
            longitude=-4.7 + index * 0.001,
        )
        for index in range(10)
    )
    first = corpus(events)
    second = corpus(tuple(reversed(events)))
    assert first.dataset_hash == second.dataset_hash
    split_a = frozen_temporal_group_split(
        first,
        split_version="split-v1",
        policy_version="policy-v1",
        created_at=NOW,
    )
    split_b = frozen_temporal_group_split(
        second,
        split_version="split-v1",
        policy_version="policy-v1",
        created_at=NOW,
    )
    assert split_a.split_hash == split_b.split_hash
    assert_no_group_leakage(split_a)


def test_frozen_models_and_test_set_protection() -> None:
    dataset = corpus((event("event-a"), event("event-b", when=NOW + timedelta(days=30))))
    split = frozen_temporal_group_split(
        dataset,
        split_version="split-v1",
        policy_version="policy-v1",
        created_at=NOW,
        development_fraction=0.4,
        validation_fraction=0.2,
    )
    with pytest.raises(ValidationError):
        split.test_frozen = False  # type: ignore[misc]
    with pytest.raises(PermissionError, match="TEST_SET_FROZEN"):
        members_for_role(split, SplitRole.TEST)
    with pytest.raises(PermissionError, match="configuración candidata"):
        authorize_test_access(
            split_hash=split.split_hash,
            candidate_configuration_hash="c" * 64,
            candidate_frozen=False,
            reason="release candidate",
            requested_at=NOW,
            actor="pytest",
        )
    audit = authorize_test_access(
        split_hash=split.split_hash,
        candidate_configuration_hash="c" * 64,
        candidate_frozen=True,
        reason="release candidate",
        requested_at=NOW,
        actor="pytest",
    )
    assert len(audit) == 64


def test_controls_require_evidence_and_are_never_true_negative() -> None:
    control = ControlWindow(
        control_id="control-a",
        event_group_id="control-group-a",
        kind=ValidationCaseKind.NO_KNOWN_FIRE_CONTROL,
        region="Castilla y León",
        start=NOW,
        end=NOW + timedelta(days=1),
        aoi_hash="d" * 64,
        area_km2=100,
        selection_method="TRUE_NEGATIVE chosen by absence",
        exclusion_checks=("official source checked",),
        sensor_coverage={"VIIRS": "AVAILABLE"},
        reference_sources=("OFFICIAL TEST FIXTURE",),
        quality="HIGH",
        evidence_hash="e" * 64,
    )
    with pytest.raises(ValueError, match="TRUE_NEGATIVE"):
        validate_control_candidates((control,))


def test_metric_eligibility_is_specific_and_does_not_drop_event() -> None:
    candidate = event("event-a")
    recall = metric_eligibility(
        candidate,
        "event_recall",
        has_replay_output=True,
        has_sensor_coverage=True,
    )
    precision = metric_eligibility(
        candidate,
        "alert_precision",
        has_replay_output=True,
        has_sensor_coverage=True,
        has_control_coverage=False,
    )
    operational_latency = metric_eligibility(
        candidate,
        "operational_availability_latency",
        has_replay_output=True,
        has_sensor_coverage=True,
    )
    assert recall.eligible is True
    assert precision.eligible is False
    assert [item.value for item in precision.reasons] == ["NO_CONTROL_COVERAGE"]
    assert operational_latency.reasons[0].value == "OPERATIONAL_AVAILABILITY_UNKNOWN"


def test_matching_records_fragmentation_merging_and_adversarial_fn() -> None:
    events = (
        event("event-a"),
        event("event-b", longitude=-4.701, latitude=40.601),
        event("event-with-no-signal", longitude=-6.0, latitude=42.0),
    )
    incidents = (
        incident("incident-shared"),
        incident("incident-fragment", longitude=-4.702, latitude=40.602),
        incident("incident-unevaluable", coverage=False),
    )
    result = match_events(events, incidents, matcher())
    assert len(result.pairs) == 2
    assert result.unmatched_event_ids == ("event-with-no-signal",)
    assert result.unevaluable_incident_ids == ("incident-unevaluable",)
    assert result.fragmentation_event_ids
    assert result.merging_incident_ids


def test_future_perimeter_metadata_does_not_change_matching() -> None:
    base = event("event-a")
    future_truth = base.model_copy(update={"has_reference_perimeter": True})
    output = (incident("incident-a"),)
    assert (
        match_events((base,), output, matcher()).pairs
        == match_events((future_truth,), output, matcher()).pairs
    )


def test_event_metrics_count_miss_and_hide_small_n_percentage() -> None:
    result = match_events(
        (event("event-a"), event("event-b", longitude=-6.0)),
        (incident("incident-a"),),
        matcher(),
    )
    recall, miss = event_detection_metrics(result)
    assert recall.numerator == 1 and recall.denominator == 2
    assert miss.numerator == 1 and miss.denominator == 2
    assert recall.status is MetricStatus.INSUFFICIENT_SAMPLE
    assert recall.value is None
    assert recall.confidence_interval is not None


def test_precision_f1_and_false_alerts_require_compatible_controls() -> None:
    result = match_events((event("event-a"),), (incident("incident-a"),), matcher())
    recall, _ = event_detection_metrics(result, minimum_sample=1)
    precision = alert_precision(result, control_coverage_sufficient=False)
    assert precision.status is MetricStatus.NO_DISPONIBLE
    assert f1_metric(precision, recall).status is MetricStatus.NO_DISPONIBLE
    area_rate, day_rate = false_alert_burden(
        2,
        evaluation_area_km2_days=4_000,
        evaluation_days=2,
    )
    assert area_rate.value == 0.5
    assert day_rate.value == 1.0


def test_latency_censoring_and_small_n_are_explicit() -> None:
    reference = HistoricalTimestamp(
        meaning="official_start_time",
        calendar_date=date(2024, 7, 1),
        precision=TimestampPrecision.DATE_ONLY,
        source="OFFICIAL TEST FIXTURE",
        timezone="Europe/Madrid",
    )
    interval = censored_latency_interval_seconds(NOW, reference)
    assert interval is not None and interval[0] < interval[1]
    latency, p90 = latency_metrics({"group-a": (3600.0,)}, seed=7)
    assert latency.status is MetricStatus.INSUFFICIENT_SAMPLE
    assert latency.value is None and p90.value is None
    localization = localization_metrics((500.0,))
    assert all(item.status is MetricStatus.INSUFFICIENT_SAMPLE for item in localization)


def test_statistics_are_reproducible_and_extreme_claims_need_large_n() -> None:
    first = group_bootstrap_interval(
        {"a": (1.0, 2.0), "b": (5.0,)},
        lambda values: float(median(values)),
        seed=42,
        iterations=200,
    )
    second = group_bootstrap_interval(
        {"a": (1.0, 2.0), "b": (5.0,)},
        lambda values: float(median(values)),
        seed=42,
        iterations=200,
    )
    assert first == second
    assert wilson_interval(10, 10).lower < 1
    assert zero_failure_lower_bound(10) < 1
    assert all_success_sample_size(0.999) > 3_000


def test_stratification_always_preserves_n() -> None:
    events = (event("event-a", area_ha=0.5), event("event-b", area_ha=500))
    result = match_events(events, (incident("incident-a"),), matcher())
    strata = stratified_recall(events, result, lambda item: fire_size_bin(item.area_ha))
    assert strata["LT_1_HA"].n == 1
    assert strata["GE_500_HA"].n == 1
    assert all(item.status is MetricStatus.INSUFFICIENT_SAMPLE for item in strata.values())


def test_report_hash_and_run_key_are_reproducible() -> None:
    result = match_events((event("event-a"),), (incident("incident-a"),), matcher())
    recall, _ = event_detection_metrics(result)
    kwargs = {
        "report_version": "test-report-v1",
        "dataset_version": "dataset-v1",
        "dataset_hash": "1" * 64,
        "split_version": "split-v1",
        "split_hash": "2" * 64,
        "split_role": SplitRole.DEVELOPMENT,
        "engine_versions": {"detection": "v1"},
        "matcher_version": matcher().matcher_version,
        "matcher_configuration_hash": matcher().configuration_hash,
        "code_commit": "3" * 40,
        "configuration": {"threshold": "PROBABLE_INCENDIO"},
        "started_at": NOW,
        "completed_at": NOW,
        "sample_counts": {"events": 1},
        "eligibility_counts": {"recall": 1},
        "excluded_counts": {},
        "metrics": (recall,),
        "failures": (),
        "limitations": ("TEST FIXTURE",),
        "unavailable_metrics": ("PR_AUC",),
    }
    first = build_validation_report(**kwargs)  # type: ignore[arg-type]
    second = build_validation_report(**kwargs)  # type: ignore[arg-type]
    assert first.report_hash == second.report_hash
    assert first.run_key == second.run_key
    assert first.verify_hash() is True
