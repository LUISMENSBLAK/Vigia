from __future__ import annotations

from collections import Counter

from vigia_ai.fusion.geodesy import geodesic_distance_m

from .models import (
    MatcherConfiguration,
    MatchingResult,
    MatchPair,
    ValidationEvent,
    ValidationIncident,
)


def match_events(
    events: tuple[ValidationEvent, ...],
    incidents: tuple[ValidationIncident, ...],
    configuration: MatcherConfiguration,
) -> MatchingResult:
    candidate_edges: list[tuple[float, float, str, str]] = []
    event_degree: Counter[str] = Counter()
    incident_degree: Counter[str] = Counter()
    evaluable_incidents = tuple(item for item in incidents if item.reference_coverage_sufficient)
    for event in events:
        for incident in evaluable_incidents:
            distance = geodesic_distance_m((event.longitude, event.latitude), incident.centroid)
            time_gap = abs((incident.first_signal_at - event.reference_time).total_seconds())
            if (
                distance <= configuration.maximum_distance_m
                and time_gap <= configuration.maximum_time_gap_seconds
            ):
                candidate_edges.append((time_gap, distance, event.event_id, incident.incident_id))
                event_degree[event.event_id] += 1
                incident_degree[incident.incident_id] += 1
    matched_events: set[str] = set()
    matched_incidents: set[str] = set()
    pairs: list[MatchPair] = []
    for time_gap, distance, event_id, incident_id in sorted(candidate_edges):
        if event_id in matched_events or incident_id in matched_incidents:
            continue
        matched_events.add(event_id)
        matched_incidents.add(incident_id)
        pairs.append(
            MatchPair(
                event_id=event_id,
                incident_id=incident_id,
                distance_m=distance,
                absolute_time_gap_seconds=time_gap,
                matcher_version=configuration.matcher_version,
                configuration_hash=configuration.configuration_hash,
            )
        )
    return MatchingResult(
        pairs=tuple(sorted(pairs, key=lambda item: (item.event_id, item.incident_id))),
        unmatched_event_ids=tuple(
            sorted(item.event_id for item in events if item.event_id not in matched_events)
        ),
        unmatched_incident_ids=tuple(
            sorted(
                item.incident_id
                for item in evaluable_incidents
                if item.incident_id not in matched_incidents
            )
        ),
        unevaluable_incident_ids=tuple(
            sorted(item.incident_id for item in incidents if not item.reference_coverage_sufficient)
        ),
        fragmentation_event_ids=tuple(
            sorted(event_id for event_id, degree in event_degree.items() if degree > 1)
        ),
        merging_incident_ids=tuple(
            sorted(incident_id for incident_id, degree in incident_degree.items() if degree > 1)
        ),
        matcher_version=configuration.matcher_version,
        configuration_hash=configuration.configuration_hash,
    )


def sensitivity_analysis(
    events: tuple[ValidationEvent, ...],
    incidents: tuple[ValidationIncident, ...],
    configurations: tuple[MatcherConfiguration, ...],
) -> dict[str, MatchingResult]:
    return {
        item.configuration_hash: match_events(events, incidents, item) for item in configurations
    }
