from __future__ import annotations

from .models import ErrorReason, FailureRecord, MatchingResult, ValidationEvent


def classify_failures(
    events: tuple[ValidationEvent, ...],
    matching: MatchingResult,
    *,
    replay_output_event_ids: set[str],
    sensor_coverage_event_ids: set[str],
) -> tuple[FailureRecord, ...]:
    by_id = {item.event_id: item for item in events}
    failures: list[FailureRecord] = []
    for event_id in matching.unmatched_event_ids:
        event = by_id[event_id]
        if event_id not in sensor_coverage_event_ids:
            reason = ErrorReason.MISSED_NO_SENSOR_SIGNAL
        elif event_id not in replay_output_event_ids:
            reason = ErrorReason.NOT_EVALUABLE
        else:
            reason = ErrorReason.MISSED_STATE_THRESHOLD
        failures.append(
            FailureRecord(
                case_id=event_id,
                event_id=event_id,
                reason_codes=(reason,),
                evidence={
                    "reference_quality": event.reference_quality,
                    "sensor_coverage_known": event_id in sensor_coverage_event_ids,
                    "replay_output_available": event_id in replay_output_event_ids,
                },
            )
        )
    for incident_id in matching.unmatched_incident_ids:
        failures.append(
            FailureRecord(
                case_id=incident_id,
                incident_id=incident_id,
                reason_codes=(ErrorReason.FALSE_SINGLE_PASS,),
                evidence={"reference_coverage_sufficient": True},
            )
        )
    for incident_id in matching.unevaluable_incident_ids:
        failures.append(
            FailureRecord(
                case_id=incident_id,
                incident_id=incident_id,
                reason_codes=(ErrorReason.NOT_EVALUABLE,),
                evidence={"reference_coverage_sufficient": False},
            )
        )
    return tuple(sorted(failures, key=lambda item: item.case_id))
