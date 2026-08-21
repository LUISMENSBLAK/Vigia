from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from .models import MatchingResult, MetricResult, MetricStatus, ValidationEvent
from .statistics import wilson_interval


def stratified_recall(
    events: tuple[ValidationEvent, ...],
    matching: MatchingResult,
    key: Callable[[ValidationEvent], str],
    *,
    minimum_sample: int = 30,
) -> dict[str, MetricResult]:
    matched = {item.event_id for item in matching.pairs}
    strata: dict[str, list[ValidationEvent]] = defaultdict(list)
    for event in events:
        strata[key(event)].append(event)
    results: dict[str, MetricResult] = {}
    for label, members in sorted(strata.items()):
        successes = sum(item.event_id in matched for item in members)
        status = (
            MetricStatus.AVAILABLE
            if len(members) >= minimum_sample
            else MetricStatus.INSUFFICIENT_SAMPLE
        )
        results[label] = MetricResult(
            metric="event_recall",
            status=status,
            unit="proportion",
            population=f"stratum={label}",
            n=len(members),
            value=successes / len(members) if status is MetricStatus.AVAILABLE else None,
            numerator=successes,
            denominator=len(members),
            confidence_interval=wilson_interval(successes, len(members)),
            reason="INSUFFICIENT_SAMPLE" if status is MetricStatus.INSUFFICIENT_SAMPLE else None,
        )
    return results


def fire_size_bin(area_ha: float | None) -> str:
    if area_ha is None:
        return "NO_DISPONIBLE"
    if area_ha < 1:
        return "LT_1_HA"
    if area_ha < 10:
        return "1_TO_LT_10_HA"
    if area_ha < 100:
        return "10_TO_LT_100_HA"
    if area_ha < 500:
        return "100_TO_LT_500_HA"
    return "GE_500_HA"
