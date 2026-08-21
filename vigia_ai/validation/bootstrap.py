from __future__ import annotations

import random
from collections.abc import Callable

from .models import ConfidenceInterval
from .statistics import percentile


def group_bootstrap_interval(
    values_by_group: dict[str, tuple[float, ...]],
    statistic: Callable[[tuple[float, ...]], float],
    *,
    seed: int,
    iterations: int = 2_000,
    confidence_level: float = 0.95,
) -> ConfidenceInterval:
    if not values_by_group:
        raise ValueError("Bootstrap requiere grupos")
    if iterations < 100:
        raise ValueError("Bootstrap requiere al menos 100 iteraciones")
    groups = tuple(sorted(values_by_group))
    generator = random.Random(seed)  # noqa: S311 - reproducibility, not security
    estimates: list[float] = []
    for _ in range(iterations):
        sampled_values: list[float] = []
        for _ in groups:
            sampled_group = generator.choice(groups)
            sampled_values.extend(values_by_group[sampled_group])
        estimates.append(statistic(tuple(sampled_values)))
    alpha = 1 - confidence_level
    ordered = tuple(sorted(estimates))
    return ConfidenceInterval(
        confidence_level=confidence_level,
        lower=percentile(ordered, alpha / 2),
        upper=percentile(ordered, 1 - alpha / 2),
        method=f"event-group percentile bootstrap; seed={seed}; iterations={iterations}",
    )
