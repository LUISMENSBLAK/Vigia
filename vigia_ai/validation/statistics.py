from __future__ import annotations

import math
from statistics import NormalDist

from .models import ConfidenceInterval


def wilson_interval(
    successes: int,
    total: int,
    *,
    confidence_level: float = 0.95,
) -> ConfidenceInterval:
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("La proporción requiere 0 <= éxitos <= total y total > 0")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level debe estar entre 0 y 1")
    z = NormalDist().inv_cdf(1 - (1 - confidence_level) / 2)
    estimate = successes / total
    denominator = 1 + z * z / total
    centre = (estimate + z * z / (2 * total)) / denominator
    margin = (
        z * math.sqrt(estimate * (1 - estimate) / total + z * z / (4 * total * total)) / denominator
    )
    return ConfidenceInterval(
        confidence_level=confidence_level,
        lower=max(0.0, centre - margin),
        upper=min(1.0, centre + margin),
        method="Wilson score interval without continuity correction",
    )


def zero_failure_lower_bound(
    total: int,
    *,
    confidence_level: float = 0.95,
    two_sided: bool = True,
) -> float:
    if total <= 0:
        raise ValueError("total debe ser positivo")
    alpha = 1 - confidence_level
    tail = alpha / 2 if two_sided else alpha
    return float(tail ** (1 / total))


def all_success_sample_size(
    target_precision: float,
    *,
    confidence_level: float = 0.95,
    two_sided: bool = True,
) -> int:
    if not 0 < target_precision < 1:
        raise ValueError("target_precision debe estar entre 0 y 1")
    alpha = 1 - confidence_level
    tail = alpha / 2 if two_sided else alpha
    return math.ceil(math.log(tail) / math.log(target_precision))


def percentile(values: tuple[float, ...], probability: float) -> float:
    if not values:
        raise ValueError("No existen valores")
    if not 0 <= probability <= 1:
        raise ValueError("probability fuera de rango")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction
