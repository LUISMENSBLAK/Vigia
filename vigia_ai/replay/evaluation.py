from __future__ import annotations

from datetime import datetime
from typing import Any

from vigia_ai.fusion.geodesy import geodesic_distance_m

from .models import ReplayIncidentSnapshot


def match_incident_to_reference(
    incident: ReplayIncidentSnapshot,
    *,
    reference_location: tuple[float, float],
    reference_time: datetime,
    maximum_distance_m: float,
    maximum_time_gap_seconds: int,
) -> dict[str, Any]:
    """Evaluation-only association. This module is never imported by ReplayEngine."""
    distance = geodesic_distance_m(incident.centroid, reference_location)
    time_gap = abs((incident.first_observation_at - reference_time).total_seconds())
    return {
        "matched": distance <= maximum_distance_m and time_gap <= maximum_time_gap_seconds,
        "distance_m": distance,
        "time_gap_seconds": time_gap,
        "method": "evaluation-spatiotemporal-v1",
    }
