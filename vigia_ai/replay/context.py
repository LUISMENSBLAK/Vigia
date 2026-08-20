from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from vigia_ai.fusion.models import ObservationEvidence, SourceFamily

from .models import ExclusionExplanation, ReplayInput, ReplayInputKind


class ReplayDataContext:
    """The only data interface visible to engines during replay."""

    def __init__(self, inputs: tuple[ReplayInput, ...]) -> None:
        identifiers = [item.input_id for item in inputs]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Los input_id del replay deben ser únicos")
        self._inputs = tuple(sorted(inputs, key=lambda item: (item.observed_at, item.input_id)))

    def explain(self, *, as_of: datetime) -> tuple[ExclusionExplanation, ...]:
        if as_of.tzinfo is None:
            raise ValueError("as_of requiere zona horaria")
        output: list[ExclusionExplanation] = []
        for item in self._inputs:
            if item.observed_at > as_of:
                reason, included = "FUTURE_OBSERVATION", False
            elif item.available_at > as_of:
                reason, included = "NOT_YET_AVAILABLE", False
            else:
                reason, included = "AVAILABLE_AT_CUTOFF", True
            output.append(
                ExclusionExplanation(
                    input_id=item.input_id,
                    included=included,
                    reason=reason,
                    observed_at=item.observed_at,
                    available_at=item.available_at,
                )
            )
        return tuple(output)

    def visible_inputs(self, *, as_of: datetime) -> tuple[ReplayInput, ...]:
        explanations = {item.input_id: item for item in self.explain(as_of=as_of)}
        return tuple(item for item in self._inputs if explanations[item.input_id].included)

    def exclusion_counts(self, *, as_of: datetime) -> dict[str, int]:
        return dict(Counter(item.reason for item in self.explain(as_of=as_of) if not item.included))

    def thermal_observations(self, *, as_of: datetime) -> list[ObservationEvidence]:
        observations: list[ObservationEvidence] = []
        for item in self.visible_inputs(as_of=as_of):
            if item.kind is not ReplayInputKind.THERMAL_OBSERVATION:
                continue
            payload = item.payload
            if item.longitude is None or item.latitude is None:
                raise RuntimeError(
                    "Contrato ReplayInput inválido: observación térmica sin posición"
                )
            observations.append(
                ObservationEvidence(
                    observation_id=item.input_id,
                    source=item.source,
                    provider=str(payload.get("provider", item.source)),
                    platform=str(payload["platform"]),
                    sensor=str(payload["sensor"]),
                    observed_at=item.observed_at,
                    received_at=item.available_at,
                    processed_at=item.available_at,
                    longitude=float(item.longitude),
                    latitude=float(item.latitude),
                    spatial_resolution_m=float(payload["spatial_resolution_m"]),
                    temporal_age_seconds=max(0, int((as_of - item.observed_at).total_seconds())),
                    confidence_raw=(
                        str(payload["confidence_raw"])
                        if payload.get("confidence_raw") is not None
                        else None
                    ),
                    frp_mw=float(payload["frp_mw"])
                    if payload.get("frp_mw") is not None
                    else None,
                    brightness_kelvin=float(payload["brightness_kelvin"])
                    if payload.get("brightness_kelvin") is not None
                    else None,
                    daynight=payload.get("daynight"),
                    quality={
                        "replay": True,
                        "availability_basis": item.availability_basis,
                        "quality_flags": item.quality_flags,
                    },
                    provenance=item.provenance,
                    source_family=SourceFamily(str(payload["source_family"])),
                )
            )
        return observations

    def availability(self, *, as_of: datetime) -> dict[str, str]:
        visible = self.visible_inputs(as_of=as_of)
        by_source = {item.source for item in visible}
        known = {item.source for item in self._inputs}
        return {source: "AVAILABLE" if source in by_source else "UNAVAILABLE" for source in known}


class TruthReferenceContext:
    """Evaluation-only reference; deliberately incompatible with ReplayDataContext."""

    def __init__(self, *, event: Any, perimeters: tuple[Any, ...] = ()) -> None:
        self._event = event
        self._perimeters = perimeters

    def evaluation_reference(self) -> dict[str, Any]:
        return {"event": self._event, "perimeters": self._perimeters}
