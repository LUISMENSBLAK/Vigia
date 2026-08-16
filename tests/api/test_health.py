from datetime import UTC, datetime

import httpx
import pytest

from services.api.vigia_api import main
from services.api.vigia_api.database import DatabaseHealth, DatabaseUnavailableError

app = main.app


async def request(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_health_is_explicit() -> None:
    response = await request("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "vigia-api"}
    assert response.headers["x-request-id"]


async def test_status_does_not_claim_live_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "database", None)
    response = await request("/v1/status")
    assert response.status_code == 200
    assert {source["state"] for source in response.json()["sources"]} == {"SIN_DATOS"}
    assert all(source["last_received_at"] is None for source in response.json()["sources"])


async def test_observations_are_empty_without_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "database", None)
    payload = (await request("/v1/fire-observations")).json()
    assert payload["features"] == []
    assert payload["metadata"]["data_state"] == "SIN_DATOS"
    assert "SUPABASE_DB_URL" in payload["metadata"]["message"]


class FakeDatabase:
    async def health(self) -> DatabaseHealth:
        return DatabaseHealth(
            checked_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
            postgis_version="3.5 test",
        )

    async def source_health(self) -> list[dict[str, object]]:
        return []

    async def fire_observations(self, *, limit: int) -> list[dict[str, object]]:
        assert limit == 50
        return [
            {
                "id": "observation-id",
                "source": "NASA FIRMS VIIRS NOAA-20",
                "platform": "N20",
                "sensor": "VIIRS",
                "observed_at": datetime(2026, 8, 16, 10, 0, tzinfo=UTC),
                "received_at": datetime(2026, 8, 16, 10, 20, tzinfo=UTC),
                "confidence_raw": "n",
                "brightness_kelvin": 331.2,
                "frp_mw": 4.8,
                "daynight": "D",
                "longitude": -4.7,
                "latitude": 40.65,
                "age_seconds": 7200,
                "provenance": {"transformation": "firms_area_csv_v1"},
            }
        ]

    async def latest_ingest_run(self) -> None:
        return None


class UnavailableDatabase(FakeDatabase):
    async def health(self) -> DatabaseHealth:
        raise DatabaseUnavailableError("sensitive driver detail")


async def test_observations_return_persisted_geojson(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "database", FakeDatabase())
    response = await request("/v1/fire-observations?limit=50")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["data_state"] == "OPERATIVO"
    assert payload["metadata"]["count"] == 1
    assert payload["features"][0]["geometry"]["coordinates"] == [-4.7, 40.65]
    assert payload["features"][0]["properties"]["confidence_raw"] == "n"
    assert payload["features"][0]["properties"]["provenance"]["transformation"] == (
        "firms_area_csv_v1"
    )


async def test_database_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "database", UnavailableDatabase())
    payload = (await request("/v1/status")).json()
    database_status = next(
        item for item in payload["sources"] if item["source"] == "Supabase / PostGIS"
    )
    assert database_status["state"] == "ERROR"
    assert database_status["error_code"] == "DATABASE_UNAVAILABLE"
    assert "sensitive" not in database_status["detail"]
