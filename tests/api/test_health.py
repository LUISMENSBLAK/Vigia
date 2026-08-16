import httpx

from services.api.vigia_api.main import app


async def request(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_health_is_explicit() -> None:
    response = await request("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "vigia-api"}
    assert response.headers["x-request-id"]


async def test_status_does_not_claim_live_sources() -> None:
    response = await request("/v1/status")
    assert response.status_code == 200
    assert {source["state"] for source in response.json()["sources"]} == {"SIN_DATOS"}
    assert all(source["last_received_at"] is None for source in response.json()["sources"])


async def test_observations_are_empty_without_ingestion() -> None:
    payload = (await request("/v1/fire-observations")).json()
    assert payload["features"] == []
    assert payload["metadata"]["data_state"] == "SIN_DATOS"
