from __future__ import annotations

import argparse
import json
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from services.api.vigia_api.config import get_settings
from services.api.vigia_api.database import VigiaDatabase
from vigia_ai.fusion.config import load_fusion_config
from vigia_ai.replay.clock import ReplayClock
from vigia_ai.replay.context import ReplayDataContext
from vigia_ai.replay.engine import ReplayEngine
from vigia_ai.replay.models import (
    ReplayCaseManifest,
    ReplayInput,
    ReplayStepOutput,
    canonical_hash,
)
from vigia_ai.replay.repository import ReplayRepository


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta o reanuda un ReplayCase persistido")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--checkpoint-dir", default="data/cache/replay-checkpoints")
    return parser.parse_args()


def _load_checkpoint(
    path: Path, *, manifest_hash: str, configuration_hash: str, code_commit: str
) -> tuple[tuple[ReplayStepOutput, ...], int, int | None, datetime | None]:
    if not path.exists():
        return (), 0, None, None
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "manifest_hash": manifest_hash,
        "configuration_hash": configuration_hash,
        "code_commit": code_commit,
    }
    if any(raw.get(key) != value for key, value in expected.items()):
        raise RuntimeError("El checkpoint pertenece a otra configuración, manifest o commit")
    raw_steps = raw.get("steps", [])
    if raw.get("checkpoint_hash") != canonical_hash(raw_steps):
        raise RuntimeError("El checkpoint está corrupto o fue modificado")
    steps = tuple(ReplayStepOutput.model_validate(item) for item in raw_steps)
    started_at = datetime.fromisoformat(str(raw["started_at"]).replace("Z", "+00:00"))
    return steps, int(raw.get("elapsed_ms", 0)), raw.get("peak_memory_bytes"), started_at


async def run() -> None:
    args = arguments()
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        raise SystemExit("NO DISPONIBLE: falta SUPABASE_DB_URL")
    database = VigiaDatabase(settings.SUPABASE_DB_URL.get_secret_value())
    try:
        case = await database.replay_case(args.case_id)
        if case is None:
            raise SystemExit("NO DISPONIBLE: ReplayCase no persistido")
        manifest = ReplayCaseManifest.model_validate(case["manifest"])
        inputs = tuple(
            ReplayInput.model_validate(item) for item in await database.replay_inputs(args.case_id)
        )
        configuration = load_fusion_config()
        checkpoint_key = canonical_hash(
            {
                "case": manifest.case_id,
                "manifest": manifest.manifest_hash,
                "configuration": configuration.configuration_hash,
                "commit": args.code_commit,
            }
        )
        checkpoint_path = Path(args.checkpoint_dir) / f"{checkpoint_key}.json"
        completed, prior_elapsed_ms, prior_peak, checkpoint_started_at = _load_checkpoint(
            checkpoint_path,
            manifest_hash=manifest.manifest_hash,
            configuration_hash=configuration.configuration_hash,
            code_commit=args.code_commit,
        )
        run_started_at = checkpoint_started_at or datetime.now(UTC)
        checkpoint_steps = list(completed)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        segment_started = perf_counter()
        tracemalloc.start()

        def checkpoint(step: ReplayStepOutput) -> None:
            checkpoint_steps.append(step)
            _, current_peak = tracemalloc.get_traced_memory()
            serialized_steps = [item.model_dump(mode="json") for item in checkpoint_steps]
            payload: dict[str, Any] = {
                "manifest_hash": manifest.manifest_hash,
                "configuration_hash": configuration.configuration_hash,
                "code_commit": args.code_commit,
                "started_at": run_started_at.isoformat(),
                "elapsed_ms": prior_elapsed_ms
                + round((perf_counter() - segment_started) * 1000),
                "peak_memory_bytes": max(prior_peak or 0, current_peak),
                "completed_step": step.step_index,
                "steps": serialized_steps,
                "checkpoint_hash": canonical_hash(serialized_steps),
            }
            temporary = checkpoint_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            temporary.replace(checkpoint_path)

        engine = ReplayEngine(
            data_context=ReplayDataContext(inputs),
            clock=ReplayClock(
                start=manifest.replay_start,
                end=manifest.replay_end,
                step=timedelta(minutes=manifest.time_step_minutes),
            ),
            fusion_config=configuration,
        )
        result = engine.run(
            manifest,
            code_commit=args.code_commit,
            completed_steps=completed,
            on_step=checkpoint,
        )
        _, current_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_ms = prior_elapsed_ms + round((perf_counter() - segment_started) * 1000)
        peak_memory = max(prior_peak or 0, current_peak)
        run_id = await ReplayRepository(database).persist_run(
            result,
            configuration=configuration.model_dump(mode="json"),
            started_at=run_started_at,
            elapsed_ms=elapsed_ms,
            approximate_peak_memory_bytes=peak_memory,
        )
        print(
            json.dumps(
                {
                    "event": "phase6_replay_completed",
                    "case_id": manifest.case_id,
                    "run_id": str(run_id),
                    "steps": len(result.steps),
                    "resumed_from_step": len(completed) - 1,
                    "observations_processed": result.observations_processed,
                    "elapsed_ms": elapsed_ms,
                    "approximate_peak_memory_bytes": peak_memory,
                    "live_state_mutated": result.live_state_mutated,
                },
                sort_keys=True,
            )
        )
    finally:
        await database.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
