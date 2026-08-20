from __future__ import annotations

from datetime import datetime
from typing import Any


def historical_geospatial_context(
    products: tuple[dict[str, Any], ...], *, as_of: datetime
) -> dict[str, dict[str, Any]]:
    """Select the latest product genuinely available at cutoff, preserving mismatch flags."""
    if as_of.tzinfo is None:
        raise ValueError("as_of requiere zona horaria")
    selected: dict[str, dict[str, Any]] = {}
    for product in products:
        observed_at = product.get("observed_at")
        available_at = product.get("available_at") or product.get("processed_at")
        if isinstance(observed_at, datetime) and observed_at > as_of:
            continue
        if isinstance(available_at, datetime) and available_at > as_of:
            continue
        layer = str(product["layer"])
        previous = selected.get(layer)
        previous_time = previous.get("observed_at") if previous else None
        if previous is None or (
            isinstance(observed_at, datetime)
            and (not isinstance(previous_time, datetime) or observed_at > previous_time)
        ):
            item = dict(product)
            reference_year = item.get("reference_year")
            if isinstance(reference_year, int) and reference_year > as_of.year:
                item["availability"] = "TEMPORAL_MISMATCH"
                flags = list(item.get("quality_flags", []))
                flags.append("REFERENCE_YEAR_AFTER_REPLAY")
                item["quality_flags"] = sorted(set(flags))
            selected[layer] = item
    return selected
