from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from vigia_ai.historical.models import HistoricalTimestamp, TimestampPrecision

from .bootstrap import group_bootstrap_interval
from .models import MetricResult, MetricStatus
from .statistics import percentile


def censored_latency_interval_seconds(
    signal_at: datetime,
    reference: HistoricalTimestamp,
) -> tuple[float, float] | None:
    if signal_at.tzinfo is None:
        raise ValueError("signal_at requiere zona horaria")
    if reference.precision is TimestampPrecision.UNKNOWN:
        return None
    if reference.precision is TimestampPrecision.DATE_ONLY:
        if reference.calendar_date is None or reference.timezone is None:
            return None
        timezone = ZoneInfo(reference.timezone)
        start = datetime.combine(reference.calendar_date, time.min, tzinfo=timezone).astimezone(UTC)
        end = (start.astimezone(timezone) + timedelta(days=1)).astimezone(UTC)
    else:
        if reference.instant is None:
            return None
        start = reference.instant
        end = (
            start + timedelta(hours=1)
            if reference.precision is TimestampPrecision.HOUR
            else start + timedelta(minutes=1)
            if reference.precision is TimestampPrecision.MINUTE
            else start
        )
    lower = (signal_at - end).total_seconds()
    upper = (signal_at - start).total_seconds()
    return (min(lower, upper), max(lower, upper))


def latency_metrics(
    seconds_by_group: dict[str, tuple[float, ...]],
    *,
    seed: int,
    minimum_sample: int = 30,
) -> tuple[MetricResult, MetricResult]:
    values = tuple(value for group in seconds_by_group.values() for value in group)
    if not values:
        unavailable = MetricResult(
            metric="median_sensor_observation_latency",
            status=MetricStatus.NO_DISPONIBLE,
            unit="seconds",
            population="matched events with compatible reference timestamps",
            n=0,
            reason="INSUFFICIENT_TEMPORAL_PRECISION",
        )
        return unavailable, unavailable.model_copy(
            update={"metric": "p90_sensor_observation_latency"}
        )
    status = (
        MetricStatus.AVAILABLE
        if len(values) >= minimum_sample
        else MetricStatus.INSUFFICIENT_SAMPLE
    )
    bootstrap = (
        group_bootstrap_interval(
            seconds_by_group,
            lambda sample: float(median(sample)),
            seed=seed,
        )
        if len(seconds_by_group) >= 2
        else None
    )
    limitation = "FIRMS histórico mide tiempo de observación, no disponibilidad operacional."
    return (
        MetricResult(
            metric="median_sensor_observation_latency",
            status=status,
            unit="seconds",
            population="matched events with compatible reference timestamps",
            n=len(values),
            value=float(median(values)) if status is MetricStatus.AVAILABLE else None,
            confidence_interval=bootstrap,
            reason="INSUFFICIENT_SAMPLE" if status is MetricStatus.INSUFFICIENT_SAMPLE else None,
            limitations=(limitation,),
        ),
        MetricResult(
            metric="p90_sensor_observation_latency",
            status=status,
            unit="seconds",
            population="matched events with compatible reference timestamps",
            n=len(values),
            value=percentile(values, 0.90) if status is MetricStatus.AVAILABLE else None,
            reason="INSUFFICIENT_SAMPLE" if status is MetricStatus.INSUFFICIENT_SAMPLE else None,
            limitations=(limitation,),
        ),
    )
