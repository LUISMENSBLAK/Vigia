from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from vigia_ai.historical.jcyl import (
    JCYL_CATALOG_URL,
    JCYL_DATASET_URL,
    JcylHistoricalClient,
    build_jcyl_corpus,
)
from vigia_ai.replay.models import canonical_hash
from vigia_ai.validation.datasets import build_corpus_version, validation_event
from vigia_ai.validation.models import SourceSnapshot
from vigia_ai.validation.splits import (
    assert_no_group_leakage,
    assign_event_groups,
    frozen_temporal_group_split,
)

DEFAULT_DATASET = Path("config/validation/historical-corpus-v1.json")
DEFAULT_SPLIT = Path("config/validation/validation-split-v1.json")
EGIF_URI = "https://datos.iepnb.es/datasets/incendios-forestales.tgz"
EGIF_CHECKSUM = "49b60e9993df0467f405136e66a84a671767dc89d80696a49a153092274045cb"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Congela dataset y split científicos Fase 7")
    parser.add_argument("--created-at", required=True, help="Timestamp ISO del snapshot real")
    parser.add_argument("--dataset-output", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split-output", type=Path, default=DEFAULT_SPLIT)
    return parser.parse_args()


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--created-at requiere zona horaria")
    return parsed.astimezone(UTC)


async def run() -> None:
    args = arguments()
    created_at = parse_datetime(args.created_at)
    payload = await JcylHistoricalClient(timeout_seconds=120).fetch()
    historical = build_jcyl_corpus(payload, retrieved_at=created_at)
    eligible = tuple(
        validation_event(event) for event in historical if event.reference_quality.value == "HIGH"
    )
    grouped = assign_event_groups(eligible)
    years = tuple(sorted({item.reference_time.year for item in grouped}))
    sources = (
        SourceSnapshot(
            source="JCYL_HISTORICAL_FIRES",
            dataset="Incendios forestales de Castilla y León",
            source_uri=JCYL_DATASET_URL,
            checksum_sha256=canonical_hash(payload),
            retrieved_at=created_at,
            raw_record_count=len(payload),
            normalized_event_count=len(historical),
            years_covered=years,
            regions_covered=("Castilla y León",),
            limitations=(
                f"Catálogo: {JCYL_CATALOG_URL}",
                "Publicación continua: el snapshot queda identificado por checksum.",
            ),
        ),
        SourceSnapshot(
            source="MITECO_EGIF_RDF",
            dataset="Estadística General de Incendios Forestales 1983-2015",
            source_uri=EGIF_URI,
            checksum_sha256=EGIF_CHECKSUM,
            retrieved_at=created_at,
            raw_record_count=509_593,
            normalized_event_count=0,
            years_covered=tuple(range(1983, 2016)),
            regions_covered=("España",),
            limitations=(
                "Fuente nacional catalogada, no incorporada a eventos evaluables v1.",
                "El RDF inspeccionado no enlaza fecha de incendio a los registros.",
                "222191 registros contienen geometría; precisión temporal insuficiente "
                "para Replay.",
            ),
        ),
    )
    corpus = build_corpus_version(
        grouped,
        (),
        dataset_version="historical-corpus-jcyl-high-v1",
        created_at=created_at,
        sources=sources,
        selection_policy_version="positive-reference-high-v1",
        coverage_limitations=(
            "Los eventos evaluables representan Castilla y León, no toda España.",
            "EGIF nacional se catalogó pero no cumple precisión temporal para este dataset.",
            "No existen controles NO_KNOWN_FIRE suficientemente respaldados en v1.",
            "2026 es una publicación en curso y no se interpreta como año completo.",
        ),
    )
    split = frozen_temporal_group_split(
        corpus,
        split_version="validation-split-v1",
        policy_version="validation-temporal-group-split-v1",
        created_at=created_at,
    )
    assert_no_group_leakage(split)
    args.dataset_output.parent.mkdir(parents=True, exist_ok=True)
    args.dataset_output.write_text(corpus.model_dump_json(indent=2) + "\n", encoding="utf-8")
    args.split_output.write_text(split.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        {
            "dataset_version": corpus.dataset_version,
            "dataset_hash": corpus.dataset_hash,
            "events": len(corpus.events),
            "controls": len(corpus.controls),
            "regions": corpus.regions_covered,
            "years": corpus.years_covered,
            "split_hash": split.split_hash,
            "split_counts": split.counts,
            "test_frozen": split.test_frozen,
        }
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
