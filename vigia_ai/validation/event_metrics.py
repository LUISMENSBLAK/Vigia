from __future__ import annotations

from .models import MatchingResult, MetricResult, MetricStatus
from .statistics import wilson_interval


def event_detection_metrics(
    matching: MatchingResult,
    *,
    minimum_sample: int = 30,
) -> tuple[MetricResult, MetricResult]:
    true_positives = len(matching.pairs)
    false_negatives = len(matching.unmatched_event_ids)
    total = true_positives + false_negatives
    if total == 0:
        unavailable = MetricResult(
            metric="event_recall",
            status=MetricStatus.NO_DISPONIBLE,
            unit="proportion",
            population="evaluable positive reference events",
            n=0,
            reason="No existen eventos positivos evaluables.",
        )
        return unavailable, unavailable.model_copy(update={"metric": "miss_rate"})
    status = MetricStatus.AVAILABLE if total >= minimum_sample else MetricStatus.INSUFFICIENT_SAMPLE
    limitation = (
        ()
        if status is MetricStatus.AVAILABLE
        else (f"N={total} es menor que la política preespecificada N={minimum_sample}.",)
    )
    recall = MetricResult(
        metric="event_recall",
        status=status,
        unit="proportion",
        population="evaluable positive reference events",
        n=total,
        value=true_positives / total if status is MetricStatus.AVAILABLE else None,
        numerator=true_positives,
        denominator=total,
        confidence_interval=wilson_interval(true_positives, total),
        reason="INSUFFICIENT_SAMPLE" if limitation else None,
        limitations=limitation,
    )
    miss_rate = MetricResult(
        metric="miss_rate",
        status=status,
        unit="proportion",
        population="evaluable positive reference events",
        n=total,
        value=false_negatives / total if status is MetricStatus.AVAILABLE else None,
        numerator=false_negatives,
        denominator=total,
        confidence_interval=wilson_interval(false_negatives, total),
        reason="INSUFFICIENT_SAMPLE" if limitation else None,
        limitations=limitation,
    )
    return recall, miss_rate


def f1_metric(precision: MetricResult, recall: MetricResult) -> MetricResult:
    if (
        precision.status is not MetricStatus.AVAILABLE
        or recall.status is not MetricStatus.AVAILABLE
        or precision.value is None
        or recall.value is None
    ):
        return MetricResult(
            metric="f1",
            status=MetricStatus.NO_DISPONIBLE,
            unit="harmonic proportion",
            population="same evaluable event/alert population",
            n=0,
            reason="Precision y recall no están definidos sobre una población compatible.",
        )
    denominator = precision.value + recall.value
    return MetricResult(
        metric="f1",
        status=MetricStatus.AVAILABLE,
        unit="harmonic proportion",
        population="same evaluable event/alert population",
        n=min(precision.n, recall.n),
        value=0.0 if denominator == 0 else 2 * precision.value * recall.value / denominator,
    )
