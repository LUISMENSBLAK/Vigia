from __future__ import annotations

from statistics import median

from .models import MetricResult, MetricStatus
from .statistics import percentile


def localization_metrics(
    distances_m: tuple[float, ...],
    *,
    minimum_sample: int = 30,
) -> tuple[MetricResult, MetricResult, MetricResult]:
    if not distances_m:
        unavailable = MetricResult(
            metric="median_localization_error",
            status=MetricStatus.NO_DISPONIBLE,
            unit="metres",
            population="matched events with spatially compatible reference",
            n=0,
            reason="INSUFFICIENT_SPATIAL_PRECISION",
        )
        return (
            unavailable,
            unavailable.model_copy(update={"metric": "p90_localization_error"}),
            unavailable.model_copy(update={"metric": "p95_localization_error"}),
        )
    status = (
        MetricStatus.AVAILABLE
        if len(distances_m) >= minimum_sample
        else MetricStatus.INSUFFICIENT_SAMPLE
    )
    reason = "INSUFFICIENT_SAMPLE" if status is MetricStatus.INSUFFICIENT_SAMPLE else None
    limitations = ("La referencia JCyL es un punto oficial aproximado, no un origen subpíxel.",)
    return (
        MetricResult(
            metric="median_localization_error",
            status=status,
            unit="metres",
            population="matched events with spatially compatible reference",
            n=len(distances_m),
            value=float(median(distances_m)) if status is MetricStatus.AVAILABLE else None,
            reason=reason,
            limitations=limitations,
        ),
        MetricResult(
            metric="p90_localization_error",
            status=status,
            unit="metres",
            population="matched events with spatially compatible reference",
            n=len(distances_m),
            value=percentile(distances_m, 0.90) if status is MetricStatus.AVAILABLE else None,
            reason=reason,
            limitations=limitations,
        ),
        MetricResult(
            metric="p95_localization_error",
            status=status,
            unit="metres",
            population="matched events with spatially compatible reference",
            n=len(distances_m),
            value=percentile(distances_m, 0.95) if status is MetricStatus.AVAILABLE else None,
            reason=reason,
            limitations=limitations,
        ),
    )
