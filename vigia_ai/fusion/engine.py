import hashlib
import json
import math
from collections import defaultdict, deque
from datetime import datetime
from statistics import mean

from .config import FusionConfig
from .geodesy import centroid, geodesic_distance_m
from .models import (
    THERMAL_SOURCE_FAMILIES,
    DataQuality,
    EvidenceItem,
    EvidenceRole,
    FusionRunSummary,
    IncidentCandidate,
    ObservationEvidence,
    PersistenceMetrics,
)

METERS_PER_LATITUDE_DEGREE = 111_320.0


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def _role(observation: ObservationEvidence) -> EvidenceRole:
    if observation.quality.get("known_heat_source_match") is True:
        return EvidenceRole.CONTRADICTING
    if observation.quality.get("reported_absence") is True:
        return EvidenceRole.CONTRADICTING
    if observation.source_family in THERMAL_SOURCE_FAMILIES:
        return EvidenceRole.CONFIRMING
    return EvidenceRole.CONTEXT


def _reason_codes(observation: ObservationEvidence, role: EvidenceRole) -> tuple[str, ...]:
    codes: list[str] = []
    if role is EvidenceRole.CONTRADICTING:
        if observation.quality.get("known_heat_source_match") is True:
            codes.append("KNOWN_HEAT_SOURCE")
        if observation.quality.get("reported_absence") is True:
            codes.append("SOURCE_CONTRADICTION")
    if observation.quality.get("degraded") is True:
        codes.append("LOW_QUALITY")
    return tuple(codes)


def _quality(items: list[EvidenceItem]) -> DataQuality:
    if any(item.observation.quality.get("degraded") is True for item in items):
        return DataQuality.DEGRADADA
    if any(
        item.observation.spatial_resolution_m is None
        or item.observation.provenance is None
        for item in items
    ):
        return DataQuality.PARCIAL
    return DataQuality.COMPLETA if items else DataQuality.DESCONOCIDA


def _persistence(
    observations: list[ObservationEvidence], window_seconds: int
) -> PersistenceMetrics:
    ordered_times = sorted({item.observed_at for item in observations})
    if len(ordered_times) == 1:
        return PersistenceMetrics(
            detection_count=len(observations),
            consecutive_windows=1,
            persistence_seconds=0,
            temporal_gap_max_seconds=0,
            temporal_gap_mean_seconds=0,
        )
    gaps = [
        int((current - previous).total_seconds())
        for previous, current in zip(ordered_times, ordered_times[1:], strict=False)
    ]
    consecutive = 1
    longest = 1
    for gap in gaps:
        consecutive = consecutive + 1 if gap <= window_seconds else 1
        longest = max(longest, consecutive)
    return PersistenceMetrics(
        detection_count=len(observations),
        consecutive_windows=longest,
        persistence_seconds=int((ordered_times[-1] - ordered_times[0]).total_seconds()),
        temporal_gap_max_seconds=max(gaps),
        temporal_gap_mean_seconds=mean(gaps),
    )


def _compatible(
    left: ObservationEvidence,
    right: ObservationEvidence,
    config: FusionConfig,
) -> bool:
    left_profile = config.source_profiles[left.source_family]
    right_profile = config.source_profiles[right.source_family]
    temporal_limit_seconds = max(
        left_profile.max_temporal_gap_minutes,
        right_profile.max_temporal_gap_minutes,
    ) * 60
    if abs((right.observed_at - left.observed_at).total_seconds()) > temporal_limit_seconds:
        return False
    association_radius_m = max(
        left_profile.association_radius_m,
        right_profile.association_radius_m,
        left.spatial_resolution_m or left_profile.spatial_resolution_m,
        right.spatial_resolution_m or right_profile.spatial_resolution_m,
    )
    return geodesic_distance_m(
        (left.longitude, left.latitude), (right.longitude, right.latitude)
    ) <= association_radius_m


def _cluster_thermal(
    observations: list[ObservationEvidence], config: FusionConfig
) -> list[list[ObservationEvidence]]:
    if not observations:
        return []
    ordered = sorted(observations, key=lambda item: (item.observed_at, item.observation_id))
    disjoint = _DisjointSet(len(ordered))
    cell_degrees = config.maximum_association_radius_m / METERS_PER_LATITUDE_DEGREE
    buckets: dict[tuple[int, int], deque[int]] = defaultdict(deque)
    max_gap_seconds = max(
        profile.max_temporal_gap_minutes
        for family, profile in config.source_profiles.items()
        if family in THERMAL_SOURCE_FAMILIES
    ) * 60

    for index, observation in enumerate(ordered):
        cell = (
            math.floor(observation.longitude / cell_degrees),
            math.floor(observation.latitude / cell_degrees),
        )
        longitude_neighbors = max(
            1,
            math.ceil(
                1 / max(math.cos(math.radians(observation.latitude)), 0.1)
            ),
        )
        for longitude_offset in range(-longitude_neighbors, longitude_neighbors + 1):
            for latitude_offset in (-1, 0, 1):
                bucket = buckets[(cell[0] + longitude_offset, cell[1] + latitude_offset)]
                while bucket and (
                    observation.observed_at - ordered[bucket[0]].observed_at
                ).total_seconds() > max_gap_seconds:
                    bucket.popleft()
                for previous_index in bucket:
                    if _compatible(ordered[previous_index], observation, config):
                        disjoint.union(previous_index, index)
        buckets[cell].append(index)

    components: dict[int, list[ObservationEvidence]] = defaultdict(list)
    for index, observation in enumerate(ordered):
        components[disjoint.find(index)].append(observation)
    return [components[key] for key in sorted(components)]


def _attach_context(
    component: list[ObservationEvidence],
    context: list[ObservationEvidence],
    config: FusionConfig,
) -> list[ObservationEvidence]:
    return [
        observation
        for observation in context
        if any(_compatible(thermal, observation, config) for thermal in component)
    ]


def _candidate(
    thermal: list[ObservationEvidence],
    context: list[ObservationEvidence],
    config: FusionConfig,
) -> IncidentCandidate:
    all_observations = sorted(
        [*thermal, *context], key=lambda item: (item.observed_at, item.observation_id)
    )
    items = [
        EvidenceItem(
            observation=observation,
            role=(role := _role(observation)),
            reason_codes=_reason_codes(observation, role),
        )
        for observation in all_observations
    ]
    center = centroid([(item.longitude, item.latitude) for item in thermal])
    extent = max(
        geodesic_distance_m(center, (item.longitude, item.latitude)) for item in thermal
    )
    identity = json.dumps(
        {
            "configuration_hash": config.configuration_hash,
            "observations": sorted(item.observation_id for item in thermal),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    candidate_id = hashlib.sha256(identity.encode()).hexdigest()
    return IncidentCandidate(
        candidate_id=candidate_id,
        observations=tuple(items),
        first_observation_at=min(item.observed_at for item in thermal),
        last_observation_at=max(item.observed_at for item in thermal),
        centroid=center,
        spatial_extent_m=extent,
        platforms=tuple(sorted({item.platform for item in thermal})),
        sensors=tuple(sorted({item.sensor for item in thermal})),
        source_families=tuple(sorted({item.source_family for item in all_observations})),
        persistence=_persistence(
            thermal, window_seconds=config.persistence_window_minutes * 60
        ),
        data_quality=_quality(items),
        configuration_hash=config.configuration_hash,
    )


def fuse_observations(
    observations: list[ObservationEvidence],
    *,
    config: FusionConfig,
    as_of: datetime,
) -> FusionRunSummary:
    if as_of.tzinfo is None:
        raise ValueError("as_of debe incluir zona horaria.")
    age_limit_seconds = config.max_age_minutes * 60
    eligible = [
        item
        for item in observations
        if item.observed_at <= as_of
        and item.received_at <= as_of
        and (item.processed_at is None or item.processed_at <= as_of)
        and 0 <= (as_of - item.observed_at).total_seconds() <= age_limit_seconds
    ]
    thermal = [item for item in eligible if item.source_family in THERMAL_SOURCE_FAMILIES]
    context = [item for item in eligible if item.source_family not in THERMAL_SOURCE_FAMILIES]
    candidates = tuple(
        _candidate(component, _attach_context(component, context, config), config)
        for component in _cluster_thermal(thermal, config)
    )
    return FusionRunSummary(
        as_of=as_of,
        configuration_hash=config.configuration_hash,
        input_observation_count=len(observations),
        eligible_observation_count=len(eligible),
        candidate_count=len(candidates),
        incident_candidate_count=sum(
            candidate.confirming_count >= config.incident_min_observations
            for candidate in candidates
        ),
        candidates=candidates,
    )
