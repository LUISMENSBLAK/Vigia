from __future__ import annotations

import httpx
import pytest

from services.api.vigia_api import main


async def request(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


class ValidationDatabase:
    async def validation_datasets(self, *, limit: int) -> list[dict[str, object]]:
        assert limit == 10
        return [
            {
                "id": "dataset-id",
                "version": "historical-corpus-jcyl-high-v1",
                "dataset_hash": "a" * 64,
                "event_count": 5866,
                "control_count": 0,
                "regions_covered": ["Castilla y León"],
                "years_covered": [2021, 2022, 2023, 2024, 2025, 2026],
                "coverage_limitations": ["No representa España"],
                "selection_policy_version": "positive-reference-high-v1",
                "frozen": True,
                "created_at": "2026-08-21T00:44:00Z",
                "published_at": "2026-08-21T00:44:00Z",
                "split_id": "split-id",
                "split_version": "validation-split-v1",
                "split_hash": "b" * 64,
                "development_count": 3520,
                "validation_count": 1174,
                "test_count": 1172,
                "test_frozen": True,
                "leakage_checked": True,
            }
        ]

    async def validation_dataset(self, dataset_id: str) -> dict[str, object] | None:
        if dataset_id == "missing":
            return None
        return {
            "id": dataset_id,
            "version": "historical-corpus-jcyl-high-v1",
            "dataset_hash": "a" * 64,
            "manifest": {"controls": []},
            "sources": [],
            "filters": {},
            "selection_policy_version": "positive-reference-high-v1",
            "event_count": 5866,
            "control_count": 0,
            "regions_covered": ["Castilla y León"],
            "years_covered": [2021],
            "coverage_limitations": ["No representa España"],
            "frozen": True,
            "created_at": "2026-08-21T00:44:00Z",
            "published_at": "2026-08-21T00:44:00Z",
        }

    async def validation_runs(self, *, limit: int) -> list[dict[str, object]]:
        assert limit == 10
        return [{"id": "run-id", "split_role": "DEVELOPMENT", "published": True}]

    async def validation_run(self, run_id: str) -> dict[str, object] | None:
        return (
            None
            if run_id == "missing"
            else {
                "id": run_id,
                "report": {"unavailable_metrics": ["PR_AUC"]},
                "published": True,
                "live_state_mutated": False,
            }
        )

    async def validation_metrics(self, run_id: str) -> list[dict[str, object]]:
        assert run_id == "run-id"
        return [
            {
                "metric_name": "event_recall",
                "availability": "INSUFFICIENT_SAMPLE",
                "n": 1,
                "value": None,
            }
        ]

    async def validation_errors(self, run_id: str) -> list[dict[str, object]]:
        assert run_id == "run-id"
        return []


async def test_validation_api_exposes_scope_n_and_unavailable_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "database", ValidationDatabase())
    datasets = (await request("/api/validation/datasets?limit=10")).json()
    runs = (await request("/api/validation/runs?limit=10")).json()
    run = (await request("/api/validation/runs/run-id")).json()
    metrics = (await request("/api/validation/runs/run-id/metrics")).json()
    errors = (await request("/api/validation/runs/run-id/errors")).json()
    assert datasets[0]["regions_covered"] == ["Castilla y León"]
    assert datasets[0]["control_count"] == 0
    assert datasets[0]["test_frozen"] is True
    assert runs[0]["split_role"] == "DEVELOPMENT"
    assert run["report"]["unavailable_metrics"] == ["PR_AUC"]
    assert metrics[0]["availability"] == "INSUFFICIENT_SAMPLE"
    assert metrics[0]["n"] == 1 and metrics[0]["value"] is None
    assert errors == []


async def test_validation_api_uses_not_available_instead_of_fake_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "database", ValidationDatabase())
    assert (await request("/api/validation/datasets/missing")).status_code == 404
    assert (await request("/api/validation/runs/missing")).status_code == 404
