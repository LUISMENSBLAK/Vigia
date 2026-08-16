from datetime import UTC, datetime, timedelta

import httpx
import pytest

from workers.eumetsat.client import (
    EumetsatAuthenticationError,
    EumetsatClient,
    MissingEumetsatCredentialsError,
)


def test_missing_eumetsat_credentials_are_explicit() -> None:
    with pytest.raises(MissingEumetsatCredentialsError, match="EUMETSAT_CONSUMER_KEY"):
        EumetsatClient(None, None)


async def test_token_is_cached_and_collection_is_url_encoded() -> None:
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/token":
            token_calls += 1
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600})
        assert request.url.path.endswith("/collections/EO:EUM:DAT:0682")
        assert request.headers["authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"collection": {"properties": {"title": "AFM"}}})

    client = EumetsatClient(
        "consumer-key",
        "consumer-secret",
        base_url="https://eumetsat.test",
        transport=httpx.MockTransport(handler),
        clock=lambda: 1000,
    )
    metadata = await client.collection_metadata("EO:EUM:DAT:0682")
    assert metadata["properties"]["title"] == "AFM"
    assert await client.access_token() == "test-token"
    assert token_calls == 1


async def test_search_uses_bounded_window_and_limit() -> None:
    start = datetime(2026, 8, 16, 10, tzinfo=UTC)
    end = start + timedelta(hours=1)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600})
        assert request.url.params["pi"] == "EO:EUM:DAT:0682"
        assert request.url.params["c"] == "3"
        assert request.url.params["dtstart"] == start.isoformat()
        assert request.url.params["dtend"] == end.isoformat()
        return httpx.Response(200, json={"totalResults": 1, "features": [{"id": "product"}]})

    client = EumetsatClient(
        "consumer-key",
        "consumer-secret",
        base_url="https://eumetsat.test",
        transport=httpx.MockTransport(handler),
    )
    payload = await client.search_products(
        "EO:EUM:DAT:0682", start=start, end=end, limit=3
    )
    assert payload["totalResults"] == 1


async def test_authentication_error_never_contains_credentials() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    client = EumetsatClient(
        "consumer-key",
        "consumer-secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EumetsatAuthenticationError) as raised:
        await client.access_token()
    assert "consumer-key" not in str(raised.value)
    assert "consumer-secret" not in str(raised.value)
