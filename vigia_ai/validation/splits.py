from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from vigia_ai.fusion.geodesy import geodesic_distance_m
from vigia_ai.replay.models import canonical_hash

from .models import (
    HistoricalCorpusVersion,
    SplitAssignment,
    SplitRole,
    ValidationEvent,
    ValidationSplitManifest,
)


class _UnionFind:
    def __init__(self, identifiers: tuple[str, ...]) -> None:
        self.parent = {item: item for item in identifiers}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        root, child = sorted((left_root, right_root))
        self.parent[child] = root


def assign_event_groups(
    events: tuple[ValidationEvent, ...],
    *,
    maximum_distance_m: float = 25_000,
    maximum_time_gap_seconds: int = 72 * 3600,
) -> tuple[ValidationEvent, ...]:
    ordered = tuple(sorted(events, key=lambda item: (item.reference_time, item.event_id)))
    union = _UnionFind(tuple(item.event_id for item in ordered))
    active_by_region: dict[str, list[ValidationEvent]] = defaultdict(list)
    for event in ordered:
        active = [
            candidate
            for candidate in active_by_region[event.region]
            if (event.reference_time - candidate.reference_time).total_seconds()
            <= maximum_time_gap_seconds
        ]
        for candidate in active:
            if not set(event.provinces).intersection(candidate.provinces):
                continue
            distance = geodesic_distance_m(
                (event.longitude, event.latitude),
                (candidate.longitude, candidate.latitude),
            )
            if distance <= maximum_distance_m:
                union.union(event.event_id, candidate.event_id)
        active.append(event)
        active_by_region[event.region] = active
    return tuple(
        event.model_copy(update={"event_group_id": f"episode-{union.find(event.event_id)[:24]}"})
        for event in sorted(ordered, key=lambda item: item.event_id)
    )


def frozen_temporal_group_split(
    corpus: HistoricalCorpusVersion,
    *,
    split_version: str,
    policy_version: str,
    created_at: datetime,
    development_fraction: float = 0.60,
    validation_fraction: float = 0.20,
) -> ValidationSplitManifest:
    if not corpus.verify_hash():
        raise ValueError("Dataset hash inválido")
    if development_fraction <= 0 or validation_fraction <= 0:
        raise ValueError("Las fracciones deben ser positivas")
    if development_fraction + validation_fraction >= 1:
        raise ValueError("Debe reservarse un periodo TEST futuro")
    by_group: dict[str, list[ValidationEvent]] = defaultdict(list)
    for event in corpus.events:
        by_group[event.event_group_id].append(event)
    ordered_groups = sorted(
        by_group.items(),
        key=lambda item: (min(event.reference_time for event in item[1]), item[0]),
    )
    total = len(corpus.events) + len(corpus.controls)
    development_limit = total * development_fraction
    validation_limit = total * (development_fraction + validation_fraction)
    assigned_count = 0
    assignments: list[SplitAssignment] = []
    for group_id, group_events in ordered_groups:
        midpoint = assigned_count + len(group_events) / 2
        role = (
            SplitRole.DEVELOPMENT
            if midpoint <= development_limit
            else SplitRole.VALIDATION
            if midpoint <= validation_limit
            else SplitRole.TEST
        )
        assignments.extend(
            SplitAssignment(member_id=event.event_id, event_group_id=group_id, role=role)
            for event in sorted(group_events, key=lambda item: item.event_id)
        )
        assigned_count += len(group_events)
    for control in sorted(corpus.controls, key=lambda item: (item.start, item.control_id)):
        midpoint = assigned_count + 0.5
        role = (
            SplitRole.DEVELOPMENT
            if midpoint <= development_limit
            else SplitRole.VALIDATION
            if midpoint <= validation_limit
            else SplitRole.TEST
        )
        assignments.append(
            SplitAssignment(
                member_id=control.control_id,
                event_group_id=control.event_group_id,
                role=role,
            )
        )
        assigned_count += 1
    ordered_assignments = tuple(sorted(assignments, key=lambda item: item.member_id))
    counts = Counter(item.role.value for item in ordered_assignments)
    payload = {
        "split_version": split_version,
        "dataset_version": corpus.dataset_version,
        "dataset_hash": corpus.dataset_hash,
        "policy_version": policy_version,
        "assignments": [item.model_dump(mode="json") for item in ordered_assignments],
        "counts": dict(sorted(counts.items())),
        "test_frozen": True,
    }
    return ValidationSplitManifest(
        split_version=split_version,
        dataset_version=corpus.dataset_version,
        dataset_hash=corpus.dataset_hash,
        policy_version=policy_version,
        assignments=ordered_assignments,
        counts=dict(sorted(counts.items())),
        created_at=created_at,
        split_hash=canonical_hash(payload),
        test_frozen=True,
    )


def assert_no_group_leakage(manifest: ValidationSplitManifest) -> None:
    roles_by_group: dict[str, set[SplitRole]] = defaultdict(set)
    for assignment in manifest.assignments:
        roles_by_group[assignment.event_group_id].add(assignment.role)
    leaked = [group for group, roles in roles_by_group.items() if len(roles) > 1]
    if leaked:
        raise ValueError(f"Group leakage detectado: {len(leaked)} grupos")


def members_for_role(
    manifest: ValidationSplitManifest,
    role: SplitRole,
    *,
    test_access_audit_id: str | None = None,
) -> tuple[str, ...]:
    if role is SplitRole.TEST and not test_access_audit_id:
        raise PermissionError("TEST_SET_FROZEN: se requiere acceso auditado")
    return tuple(item.member_id for item in manifest.assignments if item.role is role)
