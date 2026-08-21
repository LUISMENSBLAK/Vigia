from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from services.api.vigia_api.database import VigiaDatabase

from .models import (
    HistoricalCorpusVersion,
    MatchingResult,
    ValidationReport,
    ValidationSplitManifest,
)


class ValidationRepository:
    def __init__(self, database: VigiaDatabase) -> None:
        self._database = database

    async def persist_dataset_and_split(
        self,
        corpus: HistoricalCorpusVersion,
        split: ValidationSplitManifest,
    ) -> tuple[UUID, UUID]:
        if not corpus.verify_hash() or not split.verify_hash():
            raise ValueError("Dataset o split hash inválido")
        if corpus.dataset_hash != split.dataset_hash:
            raise ValueError("El split no pertenece al dataset")
        assignments = {item.member_id: item for item in split.assignments}
        async with self._database.transaction() as connection:
            dataset_id = await connection.scalar(
                text(
                    """
                    insert into vigia.validation_dataset_versions (
                      version, dataset_hash, manifest, sources, filters,
                      selection_policy_version, event_count, control_count,
                      regions_covered, years_covered, coverage_limitations,
                      frozen, created_at, published_at
                    ) values (
                      :version, :dataset_hash, cast(:manifest as jsonb),
                      cast(:sources as jsonb), cast(:filters as jsonb),
                      :policy, :events, :controls, :regions, :years,
                      :limitations, true, :created_at, :created_at
                    ) on conflict (dataset_hash) do nothing returning id
                    """
                ),
                {
                    "version": corpus.dataset_version,
                    "dataset_hash": corpus.dataset_hash,
                    "manifest": corpus.model_dump_json(),
                    "sources": json.dumps(
                        [item.model_dump(mode="json") for item in corpus.sources],
                        default=str,
                    ),
                    "filters": json.dumps(corpus.filters),
                    "policy": corpus.selection_policy_version,
                    "events": len(corpus.events),
                    "controls": len(corpus.controls),
                    "regions": list(corpus.regions_covered),
                    "years": list(corpus.years_covered),
                    "limitations": list(corpus.coverage_limitations),
                    "created_at": corpus.created_at,
                },
            )
            if dataset_id is None:
                dataset_id = await connection.scalar(
                    text(
                        "select id from vigia.validation_dataset_versions "
                        "where dataset_hash = :hash"
                    ),
                    {"hash": corpus.dataset_hash},
                )
            if not isinstance(dataset_id, UUID):
                raise RuntimeError("No se pudo persistir el dataset científico")
            split_id = await connection.scalar(
                text(
                    """
                    insert into vigia.validation_split_manifests (
                      dataset_version_id, version, policy_version, manifest,
                      split_hash, development_count, validation_count, test_count,
                      leakage_checked, test_frozen, frozen, created_at
                    ) values (
                      :dataset_id, :version, :policy, cast(:manifest as jsonb), :hash,
                      :development, :validation, :test, true, true, true, :created_at
                    ) on conflict (split_hash) do nothing returning id
                    """
                ),
                {
                    "dataset_id": dataset_id,
                    "version": split.split_version,
                    "policy": split.policy_version,
                    "manifest": split.model_dump_json(),
                    "hash": split.split_hash,
                    "development": split.counts.get("DEVELOPMENT", 0),
                    "validation": split.counts.get("VALIDATION", 0),
                    "test": split.counts.get("TEST", 0),
                    "created_at": split.created_at,
                },
            )
            if split_id is None:
                split_id = await connection.scalar(
                    text(
                        "select id from vigia.validation_split_manifests where split_hash = :hash"
                    ),
                    {"hash": split.split_hash},
                )
            if not isinstance(split_id, UUID):
                raise RuntimeError("No se pudo persistir el split científico")
            member_parameters = [
                {
                    "dataset_id": dataset_id,
                    "split_id": split_id,
                    "member_key": event.event_id,
                    "group_id": event.event_group_id,
                    "kind": event.kind.value,
                    "split_role": assignments[event.event_id].role.value,
                    "quality": event.reference_quality,
                    "reference_time": event.reference_time,
                    "longitude": event.longitude,
                    "latitude": event.latitude,
                    "metadata": event.model_dump_json(),
                }
                for event in corpus.events
            ]
            if member_parameters:
                await connection.execute(
                    text(
                        """
                        insert into vigia.validation_dataset_members (
                          dataset_version_id, split_manifest_id, member_key,
                          event_group_id, kind, split_role, historical_fire_id,
                          reference_quality, reference_time, reference_location, metadata
                        ) values (
                          :dataset_id, :split_id, :member_key, :group_id,
                          cast(:kind as vigia.validation_member_kind),
                          cast(:split_role as vigia.validation_split_role),
                          (select id from vigia.historical_fires where event_key = :member_key),
                          cast(:quality as vigia.reference_quality), :reference_time,
                          extensions.st_setsrid(extensions.st_makepoint(:longitude, :latitude),
                            4326)::extensions.geography,
                          cast(:metadata as jsonb)
                        ) on conflict (dataset_version_id, member_key) do nothing
                        """
                    ),
                    member_parameters,
                )
        return dataset_id, split_id

    async def persist_engine_version(
        self,
        *,
        name: str,
        source_commit: str,
        fusion_version: str,
        detection_version: str,
        risk_version: str,
        configuration: dict[str, object],
        configuration_hash: str,
    ) -> UUID:
        async with self._database.transaction() as connection:
            engine_id = await connection.scalar(
                text(
                    """
                    insert into vigia.validation_engine_versions (
                      name, source_commit, fusion_version, detection_version,
                      risk_version, configuration, configuration_hash,
                      automatic_confirmed_fire, frozen
                    ) values (
                      :name, :commit, :fusion, :detection, :risk,
                      cast(:configuration as jsonb), :hash, false, true
                    ) on conflict (configuration_hash) do nothing returning id
                    """
                ),
                {
                    "name": name,
                    "commit": source_commit,
                    "fusion": fusion_version,
                    "detection": detection_version,
                    "risk": risk_version,
                    "configuration": json.dumps(configuration),
                    "hash": configuration_hash,
                },
            )
            if engine_id is None:
                engine_id = await connection.scalar(
                    text(
                        "select id from vigia.validation_engine_versions "
                        "where configuration_hash = :hash"
                    ),
                    {"hash": configuration_hash},
                )
        if not isinstance(engine_id, UUID):
            raise RuntimeError("No se pudo persistir la versión de engine")
        return engine_id

    async def persist_report(
        self,
        report: ValidationReport,
        matching: MatchingResult,
        *,
        dataset_id: UUID,
        split_id: UUID,
        engine_id: UUID,
        configuration: dict[str, object],
        seed: int,
        regions: tuple[str, ...],
        temporal_start: datetime,
        temporal_end: datetime,
    ) -> UUID:
        if not report.verify_hash():
            raise ValueError("Report hash inválido")
        async with self._database.transaction() as connection:
            run_id = await connection.scalar(
                text(
                    """
                    insert into vigia.validation_runs (
                      model_version_id, started_at, completed_at, commit_sha,
                      dataset_hash, temporal_range, regions, seed, configuration,
                      sample_size, reproducible, run_key, dataset_version_id,
                      split_manifest_id, split_role, engine_version_id,
                      matcher_version, matcher_configuration,
                      matcher_configuration_hash, configuration_hash,
                      sample_counts, eligibility_counts, excluded_counts,
                      limitations, unavailable_metrics, report, report_hash,
                      published, test_access_audit_id, live_state_mutated
                    ) values (
                      null, :started_at, :completed_at, :commit, :dataset_hash,
                      tstzrange(:temporal_start, :temporal_end, '[)'), :regions,
                      :seed, cast(:configuration as jsonb), :sample_size, true,
                      :run_key, :dataset_id, :split_id,
                      cast(:split_role as vigia.validation_split_role), :engine_id,
                      :matcher_version, cast(:matcher_configuration as jsonb),
                      :matcher_hash, :configuration_hash, cast(:sample_counts as jsonb),
                      cast(:eligibility_counts as jsonb), cast(:excluded_counts as jsonb),
                      :limitations, :unavailable, cast(:report as jsonb), :report_hash,
                      true, null, false
                    ) on conflict (run_key) where run_key is not null
                    do nothing returning id
                    """
                ),
                {
                    "started_at": report.started_at,
                    "completed_at": report.completed_at,
                    "commit": report.code_commit,
                    "dataset_hash": report.dataset_hash,
                    "temporal_start": temporal_start,
                    "temporal_end": temporal_end,
                    "regions": list(regions),
                    "seed": seed,
                    "configuration": json.dumps(configuration),
                    "sample_size": report.sample_counts.get("evaluated_events", 0),
                    "run_key": report.run_key,
                    "dataset_id": dataset_id,
                    "split_id": split_id,
                    "split_role": report.split_role.value,
                    "engine_id": engine_id,
                    "matcher_version": report.matcher_version,
                    "matcher_configuration": json.dumps(
                        {"configuration_hash": report.matcher_configuration_hash}
                    ),
                    "matcher_hash": report.matcher_configuration_hash,
                    "configuration_hash": report.configuration_hash,
                    "sample_counts": json.dumps(report.sample_counts),
                    "eligibility_counts": json.dumps(report.eligibility_counts),
                    "excluded_counts": json.dumps(report.excluded_counts),
                    "limitations": list(report.limitations),
                    "unavailable": list(report.unavailable_metrics),
                    "report": report.model_dump_json(),
                    "report_hash": report.report_hash,
                },
            )
            if run_id is None:
                run_id = await connection.scalar(
                    text("select id from vigia.validation_runs where run_key = :run_key"),
                    {"run_key": report.run_key},
                )
            if not isinstance(run_id, UUID):
                raise RuntimeError("No se pudo persistir ValidationRun")
            for metric in report.metrics:
                await connection.execute(
                    text(
                        """
                        insert into vigia.validation_metric_results (
                          validation_run_id, metric_name, availability, unit,
                          population, sample_size, numerator, denominator,
                          metric_value, confidence_interval, reason, limitations
                        ) values (
                          :run_id, :name, cast(:availability as vigia.metric_availability),
                          :unit, :population, :sample_size, :numerator, :denominator,
                          :value, cast(:ci as jsonb), :reason, :limitations
                        ) on conflict (validation_run_id, metric_name, subgroup) do nothing
                        """
                    ),
                    {
                        "run_id": run_id,
                        "name": metric.metric,
                        "availability": metric.status.value,
                        "unit": metric.unit,
                        "population": metric.population,
                        "sample_size": metric.n,
                        "numerator": metric.numerator,
                        "denominator": metric.denominator,
                        "value": metric.value,
                        "ci": (
                            metric.confidence_interval.model_dump_json()
                            if metric.confidence_interval
                            else None
                        ),
                        "reason": metric.reason,
                        "limitations": list(metric.limitations),
                    },
                )
            for pair in matching.pairs:
                await connection.execute(
                    text(
                        """
                        insert into vigia.validation_matches (
                          validation_run_id, member_id, replay_incident_key,
                          distance_m, absolute_time_gap_seconds, matcher_version,
                          matcher_configuration_hash
                        ) select :run_id, member.id, :incident_id, :distance,
                          :time_gap, :matcher_version, :matcher_hash
                        from vigia.validation_dataset_members member
                        where member.dataset_version_id = :dataset_id
                          and member.member_key = :event_id
                        on conflict do nothing
                        """
                    ),
                    {
                        "run_id": run_id,
                        "dataset_id": dataset_id,
                        "event_id": pair.event_id,
                        "incident_id": pair.incident_id,
                        "distance": pair.distance_m,
                        "time_gap": pair.absolute_time_gap_seconds,
                        "matcher_version": pair.matcher_version,
                        "matcher_hash": pair.configuration_hash,
                    },
                )
            for failure in report.failures:
                await connection.execute(
                    text(
                        """
                        insert into vigia.validation_errors (
                          validation_run_id, member_key, replay_incident_key,
                          reason_codes, evidence, manual_override
                        ) values (
                          :run_id, :member_key, :incident_key, :reasons,
                          cast(:evidence as jsonb), false
                        ) on conflict do nothing
                        """
                    ),
                    {
                        "run_id": run_id,
                        "member_key": failure.event_id,
                        "incident_key": failure.incident_id,
                        "reasons": [item.value for item in failure.reason_codes],
                        "evidence": json.dumps(failure.evidence),
                    },
                )
        return run_id
