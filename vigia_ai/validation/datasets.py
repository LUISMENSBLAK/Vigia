from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Literal, cast

from vigia_ai.historical.models import (
    HistoricalFireEvent,
    ReferenceQuality,
    TimestampPrecision,
)
from vigia_ai.replay.models import canonical_hash

from .models import (
    ControlWindow,
    HistoricalCorpusVersion,
    SourceSnapshot,
    ValidationCaseKind,
    ValidationEvent,
)


def eligible_positive_event(event: HistoricalFireEvent) -> bool:
    start = event.official_start
    return bool(
        event.reference_quality is ReferenceQuality.HIGH
        and event.longitude is not None
        and event.latitude is not None
        and start is not None
        and start.instant is not None
        and start.precision in {TimestampPrecision.MINUTE, TimestampPrecision.EXACT}
    )


def validation_event(event: HistoricalFireEvent) -> ValidationEvent:
    if not eligible_positive_event(event):
        raise ValueError("El evento no cumple la referencia positiva preespecificada")
    start = event.official_start
    assert start is not None and start.instant is not None
    assert event.longitude is not None and event.latitude is not None
    precision = cast(Literal["MINUTE", "EXACT"], start.precision.value)
    return ValidationEvent(
        event_id=event.event_id,
        event_group_id=event.event_id,
        kind=ValidationCaseKind.POSITIVE_REFERENCE,
        region=event.region or "NO DISPONIBLE",
        provinces=event.province,
        reference_time=start.instant,
        temporal_precision=precision,
        longitude=event.longitude,
        latitude=event.latitude,
        spatial_precision="APPROXIMATE_POINT",
        reference_quality="HIGH",
        reference_sources=tuple(sorted({reference.dataset for reference in event.references})),
        reference_hash=event.canonical_hash(),
        area_ha=event.maximum_reported_area_ha,
        has_reference_perimeter=False,
    )


def validate_control_candidates(controls: tuple[ControlWindow, ...]) -> None:
    for control in controls:
        if "TRUE_NEGATIVE" in control.selection_method.upper():
            raise ValueError("Una ausencia de registro no puede etiquetarse TRUE_NEGATIVE")
        if not control.exclusion_checks or not control.reference_sources:
            raise ValueError("Los controles requieren comprobaciones y fuentes")


def build_corpus_version(
    events: tuple[ValidationEvent, ...],
    controls: tuple[ControlWindow, ...],
    *,
    dataset_version: str,
    created_at: datetime,
    sources: tuple[SourceSnapshot, ...],
    selection_policy_version: str,
    coverage_limitations: tuple[str, ...],
) -> HistoricalCorpusVersion:
    validate_control_candidates(controls)
    ordered_events = tuple(sorted(events, key=lambda item: item.event_id))
    ordered_controls = tuple(sorted(controls, key=lambda item: item.control_id))
    regions = tuple(
        sorted(
            {item.region for item in ordered_events} | {item.region for item in ordered_controls}
        )
    )
    years = tuple(sorted({item.reference_time.year for item in ordered_events}))
    region_counts = Counter(item.region for item in ordered_events)
    filters = {
        "positive_reference": {
            "quality": "HIGH",
            "required": ["existence", "minute_or_exact_time", "coordinates"],
        },
        "controls": {
            "label": "NO_KNOWN_FIRE_CONTROL",
            "required": ["selection_method", "exclusion_checks", "sensor_coverage"],
        },
    }
    payload = {
        "dataset_version": dataset_version,
        "sources": [item.model_dump(mode="json") for item in sources],
        "events": [item.model_dump(mode="json") for item in ordered_events],
        "controls": [item.model_dump(mode="json") for item in ordered_controls],
        "filters": filters,
        "selection_policy_version": selection_policy_version,
        "regions_covered": regions,
        "years_covered": years,
        "events_per_region": dict(sorted(region_counts.items())),
        "coverage_limitations": coverage_limitations,
    }
    return HistoricalCorpusVersion(
        dataset_version=dataset_version,
        created_at=created_at,
        sources=sources,
        events=ordered_events,
        controls=ordered_controls,
        filters=filters,
        selection_policy_version=selection_policy_version,
        regions_covered=regions,
        years_covered=years,
        events_per_region=dict(sorted(region_counts.items())),
        coverage_limitations=coverage_limitations,
        dataset_hash=canonical_hash(payload),
        frozen=True,
    )
