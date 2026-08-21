from __future__ import annotations

from datetime import datetime
from typing import Any

from vigia_ai.replay.models import canonical_hash

from .models import (
    FailureRecord,
    MetricResult,
    SplitRole,
    ValidationReport,
)


def build_validation_report(
    *,
    report_version: str,
    dataset_version: str,
    dataset_hash: str,
    split_version: str,
    split_hash: str,
    split_role: SplitRole,
    engine_versions: dict[str, str],
    matcher_version: str,
    matcher_configuration_hash: str,
    code_commit: str,
    configuration: dict[str, Any],
    started_at: datetime,
    completed_at: datetime,
    sample_counts: dict[str, int],
    eligibility_counts: dict[str, int],
    excluded_counts: dict[str, int],
    metrics: tuple[MetricResult, ...],
    failures: tuple[FailureRecord, ...],
    limitations: tuple[str, ...],
    unavailable_metrics: tuple[str, ...],
    test_access_audit_id: str | None = None,
) -> ValidationReport:
    configuration_hash = canonical_hash(configuration)
    run_key = canonical_hash(
        {
            "dataset_hash": dataset_hash,
            "split_hash": split_hash,
            "split_role": split_role,
            "engine_versions": engine_versions,
            "matcher_configuration_hash": matcher_configuration_hash,
            "code_commit": code_commit,
            "configuration_hash": configuration_hash,
        }
    )
    payload: dict[str, Any] = {
        "report_version": report_version,
        "run_key": run_key,
        "dataset_version": dataset_version,
        "dataset_hash": dataset_hash,
        "split_version": split_version,
        "split_hash": split_hash,
        "split_role": split_role,
        "engine_versions": dict(sorted(engine_versions.items())),
        "matcher_version": matcher_version,
        "matcher_configuration_hash": matcher_configuration_hash,
        "code_commit": code_commit,
        "configuration_hash": configuration_hash,
        "started_at": started_at,
        "completed_at": completed_at,
        "sample_counts": dict(sorted(sample_counts.items())),
        "eligibility_counts": dict(sorted(eligibility_counts.items())),
        "excluded_counts": dict(sorted(excluded_counts.items())),
        "metrics": metrics,
        "failures": failures,
        "limitations": limitations,
        "unavailable_metrics": unavailable_metrics,
        "test_access_audit_id": test_access_audit_id,
        "live_state_mutated": False,
    }
    draft = ValidationReport(report_hash="0" * 64, **payload)
    return draft.model_copy(update={"report_hash": canonical_hash(draft.hash_payload())})
