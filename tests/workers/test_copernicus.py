from datetime import UTC, datetime

import httpx
import pytest

from workers.copernicus.client import (
    SENTINEL_COLLECTIONS,
    CopernicusClient,
    MissingCopernicusCredentialsError,
    sentinel_2_index_request,
)


def test_missing_copernicus_credentials_are_explicit() -> None:
    with pytest.raises(MissingCopernicusCredentialsError, match="COPERNICUS_CLIENT_ID"):
        CopernicusClient(
            None,
            None,
            token_url="https://identity.test/token",  # noqa: S106
            base_url="https://sh.test",
        )


async def test_access_token_is_reused_until_expiry() -> None:
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        assert request.url.path == "/token"
        token_calls += 1
        return httpx.Response(200, json={"access_token": "token-value", "expires_in": 600})

    client = CopernicusClient(
        "client-id",
        "client-secret",
        token_url="https://identity.test/token",  # noqa: S106
        base_url="https://sh.test",
        transport=httpx.MockTransport(handler),
        clock=lambda: 1000,
    )
    assert await client.access_token() == "token-value"
    assert await client.access_token() == "token-value"
    assert token_calls == 1


async def test_process_returns_only_a_valid_tiff() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "token-value", "expires_in": 600})
        assert request.url.path == "/api/v1/process"
        assert request.headers["authorization"] == "Bearer token-value"
        return httpx.Response(200, content=b"II*\x00test", headers={"content-type": "image/tiff"})

    client = CopernicusClient(
        "client-id",
        "client-secret",
        token_url="https://identity.test/token",  # noqa: S106
        base_url="https://sh.test",
        transport=httpx.MockTransport(handler),
    )
    assert await client.process({"small": True}) == b"II*\x00test"


def test_sentinel_index_request_uses_aoi_window_and_no_full_scene() -> None:
    request = sentinel_2_index_request(
        bbox=(-5.0, 40.0, -4.0, 41.0),
        start=datetime(2026, 8, 1, tzinfo=UTC),
        end=datetime(2026, 8, 2, tzinfo=UTC),
        width=512,
        height=512,
    )
    assert request["input"]["bounds"]["bbox"] == [-5.0, 40.0, -4.0, 41.0]
    assert request["input"]["data"][0]["type"] == SENTINEL_COLLECTIONS["sentinel-2"]
    assert "B08" in request["evalscript"]
    assert "B11" in request["evalscript"]
    assert "B12" in request["evalscript"]
    assert "SCL" in request["evalscript"]
    assert request["input"]["data"][0]["dataFilter"]["maxCloudCoverage"] == 30
