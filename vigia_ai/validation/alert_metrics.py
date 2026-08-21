from __future__ import annotations

from .models import MatchingResult, MetricResult, MetricStatus
from .statistics import wilson_interval


def alert_precision(
    matching: MatchingResult,
    *,
    control_coverage_sufficient: bool,
    minimum_sample: int = 30,
) -> MetricResult:
    if not control_coverage_sufficient:
        return MetricResult(
            metric="alert_precision",
            status=MetricStatus.NO_DISPONIBLE,
            unit="proportion",
            population="evaluable VIGÍA incidents",
            n=0,
            reason="NO_CONTROL_COVERAGE",
            limitations=(
                "Los incidentes sin referencia suficiente no se convierten automáticamente en FP.",
            ),
        )
    matched = len(matching.pairs)
    false_alerts = len(matching.unmatched_incident_ids)
    total = matched + false_alerts
    if total == 0:
        return MetricResult(
            metric="alert_precision",
            status=MetricStatus.NO_DISPONIBLE,
            unit="proportion",
            population="evaluable VIGÍA incidents",
            n=0,
            reason="No existen incidentes evaluables.",
        )
    status = MetricStatus.AVAILABLE if total >= minimum_sample else MetricStatus.INSUFFICIENT_SAMPLE
    return MetricResult(
        metric="alert_precision",
        status=status,
        unit="proportion",
        population="evaluable VIGÍA incidents",
        n=total,
        value=matched / total if status is MetricStatus.AVAILABLE else None,
        numerator=matched,
        denominator=total,
        confidence_interval=wilson_interval(matched, total),
        reason="INSUFFICIENT_SAMPLE" if status is MetricStatus.INSUFFICIENT_SAMPLE else None,
    )


def false_alert_burden(
    false_incidents: int,
    *,
    evaluation_area_km2_days: float | None,
    evaluation_days: float | None,
) -> tuple[MetricResult, MetricResult]:
    if (
        evaluation_area_km2_days is None
        or evaluation_area_km2_days <= 0
        or evaluation_days is None
        or evaluation_days <= 0
    ):
        unavailable = MetricResult(
            metric="false_alerts_per_1000_km2_day",
            status=MetricStatus.NO_DISPONIBLE,
            unit="incidents / 1000 km²-day",
            population="evaluable control coverage",
            n=0,
            reason="NO_CONTROL_COVERAGE",
        )
        return unavailable, unavailable.model_copy(
            update={"metric": "false_alerts_per_day", "unit": "incidents / day"}
        )
    return (
        MetricResult(
            metric="false_alerts_per_1000_km2_day",
            status=MetricStatus.AVAILABLE,
            unit="incidents / 1000 km²-day",
            population="evaluable control coverage",
            n=false_incidents,
            value=false_incidents * 1000 / evaluation_area_km2_days,
        ),
        MetricResult(
            metric="false_alerts_per_day",
            status=MetricStatus.AVAILABLE,
            unit="incidents / day",
            population="evaluable control coverage",
            n=false_incidents,
            value=false_incidents / evaluation_days,
        ),
    )
