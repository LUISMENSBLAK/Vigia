from __future__ import annotations

from .models import EligibilityDecision, EligibilityReason, ValidationEvent


def metric_eligibility(
    event: ValidationEvent,
    metric: str,
    *,
    has_replay_output: bool,
    has_sensor_coverage: bool,
    has_control_coverage: bool = False,
    operational_availability_known: bool = False,
    has_risk_value: bool = False,
) -> EligibilityDecision:
    reasons: list[EligibilityReason] = []
    if not has_replay_output:
        reasons.append(EligibilityReason.NO_REPLAY_OUTPUT)
    if metric in {"event_recall", "sensor_observation_latency", "localization"}:
        if not has_sensor_coverage:
            reasons.append(EligibilityReason.NO_SENSOR_COVERAGE)
    if metric in {"sensor_observation_latency", "operational_availability_latency"}:
        if event.temporal_precision not in {"MINUTE", "EXACT"}:
            reasons.append(EligibilityReason.INSUFFICIENT_TEMPORAL_PRECISION)
    if metric == "operational_availability_latency" and not operational_availability_known:
        reasons.append(EligibilityReason.OPERATIONAL_AVAILABILITY_UNKNOWN)
    if metric == "localization" and event.spatial_precision not in {
        "APPROXIMATE_POINT",
        "INITIAL_POINT",
        "PERIMETER",
    }:
        reasons.append(EligibilityReason.INSUFFICIENT_SPATIAL_PRECISION)
    if metric in {"perimeter_iou", "hausdorff", "area_error"} and not event.has_reference_perimeter:
        reasons.append(EligibilityReason.NO_REFERENCE_PERIMETER)
    if metric in {"alert_precision", "false_alert_rate"} and not has_control_coverage:
        reasons.append(EligibilityReason.NO_CONTROL_COVERAGE)
    if metric == "risk_discrimination" and not has_risk_value:
        reasons.append(EligibilityReason.NO_RISK_VALUE)
    return EligibilityDecision(
        eligible=not reasons,
        reasons=tuple(reasons) if reasons else (EligibilityReason.ELIGIBLE,),
    )
