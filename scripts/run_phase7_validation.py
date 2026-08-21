from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg

from services.api.vigia_api.config import get_settings
from services.api.vigia_api.database import VigiaDatabase
from vigia_ai.validation.alert_metrics import alert_precision, false_alert_burden
from vigia_ai.validation.event_metrics import event_detection_metrics, f1_metric
from vigia_ai.validation.failures import classify_failures
from vigia_ai.validation.latency import latency_metrics
from vigia_ai.validation.localization import localization_metrics
from vigia_ai.validation.matching import match_events, sensitivity_analysis
from vigia_ai.validation.models import (
    HistoricalCorpusVersion,
    MatcherConfiguration,
    MetricResult,
    MetricStatus,
    SplitRole,
    ValidationIncident,
    ValidationSplitManifest,
)
from vigia_ai.validation.reports import build_validation_report
from vigia_ai.validation.repository import ValidationRepository
from vigia_ai.validation.splits import members_for_role
from vigia_ai.validation.statistics import wilson_interval

DATASET_PATH = Path("config/validation/historical-corpus-v1.json")
SPLIT_PATH = Path("config/validation/validation-split-v1.json")
CONFIG_PATH = Path("config/validation/scientific-validation-v1.json")
REPORT_PATH = Path("docs/reports/baseline-validation-v1.json")
STATE_ORDER = {
    "VIGILANCIA": 0,
    "ANOMALIA": 1,
    "POSIBLE_IGNICION": 2,
    "PROBABLE_INCENDIO": 3,
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta Validation Baseline v1")
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--run-at", required=True)
    parser.add_argument(
        "--split-role",
        choices=("DEVELOPMENT", "VALIDATION"),
        default="DEVELOPMENT",
        help="TEST está deliberadamente excluido de este comando de desarrollo.",
    )
    parser.add_argument("--report-output", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--run-at requiere zona horaria")
    return parsed.astimezone(UTC)


def load_artifacts() -> tuple[HistoricalCorpusVersion, ValidationSplitManifest, dict[str, Any]]:
    corpus = HistoricalCorpusVersion.model_validate_json(DATASET_PATH.read_text(encoding="utf-8"))
    split = ValidationSplitManifest.model_validate_json(SPLIT_PATH.read_text(encoding="utf-8"))
    configuration: dict[str, Any] = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not corpus.verify_hash() or not split.verify_hash():
        raise ValueError("Dataset/split congelado con hash inválido")
    return corpus, split, configuration


async def replay_incidents(
    connection: asyncpg.Connection,
    member_ids: tuple[str, ...],
) -> tuple[tuple[ValidationIncident, ...], set[str], tuple[str, ...]]:
    rows = await connection.fetch(
        """
        with latest_run as (
          select distinct on (run.case_id) run.id, run.case_id, run.code_commit
          from vigia.replay_runs run
          where run.state = 'SUCCEEDED'
          order by run.case_id, run.started_at desc
        )
        select historical.event_key, case_row.case_key, latest.code_commit,
          step.step_index, incident.value as incident
        from latest_run latest
        join vigia.replay_cases case_row on case_row.id = latest.case_id
        join vigia.historical_fires historical on historical.id = case_row.historical_fire_id
        join vigia.replay_steps step on step.replay_run_id = latest.id
        cross join lateral jsonb_array_elements(step.incidents) incident(value)
        where historical.event_key = any($1::text[])
        order by historical.event_key, step.step_index,
          incident.value->>'replay_incident_id'
        """,
        member_ids,
    )
    latest_by_incident: dict[tuple[str, str], dict[str, Any]] = {}
    replay_output_events: set[str] = set()
    replay_commits: set[str] = set()
    for row in rows:
        event_id = str(row["event_key"])
        case_id = str(row["case_key"])
        payload = dict(row["incident"])
        incident_id = str(payload["replay_incident_id"])
        replay_output_events.add(event_id)
        replay_commits.add(str(row["code_commit"]))
        key = (event_id, incident_id)
        existing = latest_by_incident.get(key)
        if (
            existing is None
            or STATE_ORDER[str(payload["state"])] > STATE_ORDER[str(existing["state"])]
        ):
            payload["case_id"] = case_id
            latest_by_incident[key] = payload
    incidents = tuple(
        ValidationIncident(
            incident_id=f"{event_id}:{payload['replay_incident_id']}",
            case_id=str(payload["case_id"]),
            state=str(payload["state"]),  # type: ignore[arg-type]
            centroid=tuple(payload["centroid"]),  # type: ignore[arg-type]
            first_signal_at=payload["first_observation_at"],
            last_signal_at=payload["last_observation_at"],
            source_families=tuple(payload["source_families"]),
            reference_coverage_sufficient=True,
        )
        for (event_id, _), payload in sorted(latest_by_incident.items())
    )
    return incidents, replay_output_events, tuple(sorted(replay_commits))


def matcher_configuration(payload: dict[str, Any]) -> MatcherConfiguration:
    return MatcherConfiguration.model_validate(payload)


def unavailable_metric(metric: str, reason: str, population: str) -> MetricResult:
    return MetricResult(
        metric=metric,
        status=MetricStatus.NO_DISPONIBLE,
        unit="NO_DISPONIBLE",
        population=population,
        n=0,
        reason=reason,
    )


async def run() -> None:
    args = arguments()
    run_at = parse_datetime(args.run_at)
    corpus, split, configuration = load_artifacts()
    role = SplitRole(args.split_role)
    selected_ids = members_for_role(split, role)
    selected_id_set = set(selected_ids)
    selected_events = tuple(event for event in corpus.events if event.event_id in selected_id_set)
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        raise SystemExit("NO DISPONIBLE: falta SUPABASE_DB_URL")
    connection = await asyncpg.connect(
        settings.SUPABASE_DB_URL.get_secret_value(), timeout=20, command_timeout=180
    )
    try:
        incidents, replay_output_ids, replay_commits = await replay_incidents(
            connection, selected_ids
        )
    finally:
        await connection.close()
    evaluated_events = tuple(
        event for event in selected_events if event.event_id in replay_output_ids
    )
    primary_config = matcher_configuration(configuration["primary_matcher"])
    probable_incidents = tuple(
        item for item in incidents if STATE_ORDER[item.state] >= STATE_ORDER["PROBABLE_INCENDIO"]
    )
    primary_matching = match_events(evaluated_events, probable_incidents, primary_config)

    metrics: list[MetricResult] = []
    recall, miss_rate = event_detection_metrics(primary_matching)
    metrics.extend((recall, miss_rate))
    precision = alert_precision(primary_matching, control_coverage_sufficient=False)
    metrics.append(precision)
    metrics.append(f1_metric(precision, recall))
    metrics.extend(
        false_alert_burden(
            len(primary_matching.unmatched_incident_ids),
            evaluation_area_km2_days=None,
            evaluation_days=None,
        )
    )

    event_by_id = {item.event_id: item for item in evaluated_events}
    incident_by_id = {item.incident_id: item for item in probable_incidents}
    latency_by_group: dict[str, tuple[float, ...]] = {}
    for pair in primary_matching.pairs:
        event = event_by_id[pair.event_id]
        incident = incident_by_id[pair.incident_id]
        latency_by_group[event.event_group_id] = (
            (incident.first_signal_at - event.reference_time).total_seconds(),
        )
    median_latency, p90_latency = latency_metrics(
        latency_by_group,
        seed=int(configuration["statistics"]["bootstrap"]["seed"]),
    )
    metrics.extend((median_latency, p90_latency))
    metrics.extend(localization_metrics(tuple(pair.distance_m for pair in primary_matching.pairs)))
    metrics.extend(
        (
            unavailable_metric(
                "operational_availability_latency",
                "FIRMS histórico no conserva disponibilidad operacional.",
                "matched historical events",
            ),
            unavailable_metric(
                "risk_discrimination",
                "NO_RISK_VALUE y NO_CONTROL_COVERAGE",
                "positive events and comparable controls",
            ),
            MetricResult(
                metric="replay_materialization_coverage_rate",
                status=MetricStatus.AVAILABLE,
                unit="proportion",
                population=f"{role.value} positive references",
                n=len(selected_events),
                value=len(evaluated_events) / len(selected_events),
                numerator=len(evaluated_events),
                denominator=len(selected_events),
                confidence_interval=wilson_interval(len(evaluated_events), len(selected_events)),
                limitations=("Mide cobertura de replay materializado, no rendimiento.",),
            ),
        )
    )

    threshold_results: dict[str, dict[str, int]] = {}
    for state in configuration["state_thresholds"]:
        threshold_incidents = tuple(
            item for item in incidents if STATE_ORDER[item.state] >= STATE_ORDER[state]
        )
        result = match_events(evaluated_events, threshold_incidents, primary_config)
        threshold_recall, _ = event_detection_metrics(result)
        metrics.append(
            threshold_recall.model_copy(update={"metric": f"event_recall_at_{state.casefold()}"})
        )
        threshold_results[state] = {
            "matched_events": len(result.pairs),
            "missed_events": len(result.unmatched_event_ids),
            "incidents": len(threshold_incidents),
        }

    sensitivity_configs = tuple(
        MatcherConfiguration(
            matcher_version="spatiotemporal-one-to-one-v1",
            maximum_distance_m=float(item["maximum_distance_m"]),
            maximum_time_gap_seconds=int(item["maximum_time_gap_seconds"]),
        )
        for item in configuration["sensitivity_grid"]
    )
    sensitivity = sensitivity_analysis(evaluated_events, probable_incidents, sensitivity_configs)
    sensitivity_counts = {
        key: {
            "matches": len(value.pairs),
            "unmatched_events": len(value.unmatched_event_ids),
            "unmatched_incidents": len(value.unmatched_incident_ids),
        }
        for key, value in sorted(sensitivity.items())
    }
    run_configuration = {
        "protocol": configuration,
        "threshold_results": threshold_results,
        "sensitivity_results": sensitivity_counts,
        "replay_run_commits": replay_commits,
    }
    failures = classify_failures(
        evaluated_events,
        primary_matching,
        replay_output_event_ids=replay_output_ids,
        sensor_coverage_event_ids=replay_output_ids,
    )
    unavailable = (
        "PR_AUC",
        "ROC_AUC",
        "BRIER_SCORE",
        "ECE",
        "CALIBRATION",
        "OPERATIONAL_AVAILABILITY_LATENCY",
        "PERIMETER_IOU",
        "HAUSDORFF_DISTANCE",
        "AREA_ERROR",
        "ALERT_PRECISION",
        "FALSE_ALERT_BURDEN",
        "RISK_DISCRIMINATION",
    )
    report = build_validation_report(
        report_version="validation-report-v1",
        dataset_version=corpus.dataset_version,
        dataset_hash=corpus.dataset_hash,
        split_version=split.split_version,
        split_hash=split.split_hash,
        split_role=role,
        engine_versions={
            "fusion": configuration["baseline"]["fusion_version"],
            "detection": configuration["baseline"]["detection_rule_version"],
            "replay": "replay-v1",
            "risk": "risk-baseline-v1",
        },
        matcher_version=primary_config.matcher_version,
        matcher_configuration_hash=primary_config.configuration_hash,
        code_commit=args.code_commit,
        configuration=run_configuration,
        started_at=run_at,
        completed_at=run_at,
        sample_counts={
            "dataset_events": len(corpus.events),
            "dataset_controls": len(corpus.controls),
            "split_events": len(selected_events),
            "evaluated_events": len(evaluated_events),
            "replay_incidents_at_probable": len(probable_incidents),
            "matched_events": len(primary_matching.pairs),
            "missed_events": len(primary_matching.unmatched_event_ids),
        },
        eligibility_counts={
            "event_detection": len(evaluated_events),
            "sensor_observation_latency": len(primary_matching.pairs),
            "localization": len(primary_matching.pairs),
            "alert_precision": 0,
            "controls": 0,
        },
        excluded_counts={
            "no_replay_output": len(selected_events) - len(evaluated_events),
            "no_control_coverage": len(incidents),
            "test_accesses": 0,
        },
        metrics=tuple(metrics),
        failures=failures,
        limitations=(
            "El dataset evaluable v1 representa Castilla y León, no España.",
            f"Replay materializado para {len(evaluated_events)} de {len(selected_events)} "
            f"referencias {role.value}; no soporta claims de rendimiento.",
            "No existen controles respaldados; precision y falsas alertas no son calculables.",
            "FIRMS histórico no permite latencia operacional.",
            "TEST permanece congelado y no fue ejecutado.",
        ),
        unavailable_metrics=unavailable,
    )
    database = VigiaDatabase(settings.SUPABASE_DB_URL.get_secret_value())
    try:
        repository = ValidationRepository(database)
        dataset_id, split_id = await repository.persist_dataset_and_split(corpus, split)
        engine_id = await repository.persist_engine_version(
            name=configuration["baseline"]["name"],
            source_commit=configuration["baseline"]["source_commit"],
            fusion_version=configuration["baseline"]["fusion_version"],
            detection_version=configuration["baseline"]["detection_rule_version"],
            risk_version="risk-baseline-v1",
            configuration=configuration["baseline"],
            configuration_hash=configuration["baseline"]["fusion_configuration_hash"],
        )
        temporal_start = min(item.reference_time for item in selected_events)
        temporal_end = max(item.reference_time for item in selected_events) + timedelta(minutes=1)
        run_id = await repository.persist_report(
            report,
            primary_matching,
            dataset_id=dataset_id,
            split_id=split_id,
            engine_id=engine_id,
            configuration=run_configuration,
            seed=int(configuration["statistics"]["bootstrap"]["seed"]),
            regions=corpus.regions_covered,
            temporal_start=temporal_start,
            temporal_end=temporal_end,
        )
    finally:
        await database.close()
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "event": "phase7_validation_completed",
                "run_id": str(run_id),
                "run_key": report.run_key,
                "report_hash": report.report_hash,
                "dataset_hash": report.dataset_hash,
                "split_hash": report.split_hash,
                "split_role": report.split_role.value,
                "test_accessed": False,
                "sample_counts": report.sample_counts,
                "unavailable_metrics": report.unavailable_metrics,
                "live_state_mutated": report.live_state_mutated,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(run())
