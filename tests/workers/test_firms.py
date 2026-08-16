from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest

from workers.firms.vigia_firms.client import (
    FirmsClient,
    FirmsHTTPError,
    FirmsPayloadError,
    FirmsQuotaError,
    FirmsSource,
    FirmsTimeoutError,
    MissingFirmsKeyError,
    parse_firms_csv,
)
from workers.firms.vigia_firms.repository import FirmsRepository, IngestRun


def test_missing_key_fails_with_exact_variable() -> None:
    with pytest.raises(MissingFirmsKeyError, match="NASA_FIRMS_MAP_KEY"):
        FirmsClient(None)


def test_parses_firms_timestamp_as_utc() -> None:
    payload = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,bright_ti4,frp,daynight\n"
        "40.6500,-4.7000,2026-08-14,0731,N20,VIIRS,n,331.2,4.8,D\n"
    )
    received_at = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)
    rows = parse_firms_csv(payload, FirmsSource.VIIRS_NOAA20_NRT, received_at=received_at)
    assert len(rows) == 1
    assert rows[0].acquired_at == datetime(2026, 8, 14, 7, 31, tzinfo=UTC)
    assert rows[0].source is FirmsSource.VIIRS_NOAA20_NRT
    assert rows[0].frp == 4.8
    assert rows[0].confidence == "n"
    assert rows[0].raw_properties["bright_ti4"] == "331.2"
    assert len(rows[0].external_id) == 64


def test_external_id_is_stable_for_the_same_observation() -> None:
    payload = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence\n"
        "40.6500,-4.7000,2026-08-14,0731,N20,VIIRS,n\n"
    )
    received_at = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)
    first = parse_firms_csv(
        payload, FirmsSource.VIIRS_NOAA20_NRT, received_at=received_at
    )[0]
    second = parse_firms_csv(
        payload, FirmsSource.VIIRS_NOAA20_NRT, received_at=received_at
    )[0]
    assert first.external_id == second.external_id


def test_rejects_malformed_payload() -> None:
    with pytest.raises(FirmsPayloadError, match="columnas obligatorias"):
        parse_firms_csv(
            "error,message\ninvalid,request\n",
            FirmsSource.MODIS_NRT,
            received_at=datetime.now(UTC),
        )


async def test_maps_timeout_without_exposing_request_url() -> None:
    async def timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    client = FirmsClient("test-key", transport=httpx.MockTransport(timeout))
    with pytest.raises(FirmsTimeoutError, match="tiempo límite") as raised:
        await client.fetch_area(FirmsSource.MODIS_NRT)
    assert "test-key" not in str(raised.value)


async def test_maps_quota_response() -> None:
    def quota(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="quota")

    client = FirmsClient("test-key", transport=httpx.MockTransport(quota))
    with pytest.raises(FirmsQuotaError, match="cuota"):
        await client.fetch_area(FirmsSource.VIIRS_SNPP_NRT)


async def test_maps_http_error_without_response_body() -> None:
    def failure(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="internal details")

    client = FirmsClient("test-key", transport=httpx.MockTransport(failure))
    with pytest.raises(FirmsHTTPError, match="HTTP 503") as raised:
        await client.fetch_area(FirmsSource.VIIRS_NOAA21_NRT)
    assert "internal details" not in str(raised.value)


class RecordingConnection:
    def __init__(self) -> None:
        self.parameters: list[dict[str, Any]] = []

    async def execute(self, _: object, parameters: dict[str, Any]) -> None:
        self.parameters.append(parameters)


class RecordingDatabase:
    def __init__(self) -> None:
        self.connection = RecordingConnection()

    @asynccontextmanager
    async def transaction(self):  # type: ignore[no-untyped-def]
        yield self.connection


async def test_successful_empty_firms_check_is_operational() -> None:
    database = RecordingDatabase()
    repository = FirmsRepository(database)  # type: ignore[arg-type]
    now = datetime.now(UTC)
    run = IngestRun(id=uuid4(), source_id=uuid4(), started_at=now)
    result = await repository.persist(run, [], code_commit="test", finished_at=now)
    health = next(item for item in database.connection.parameters if "state" in item)
    assert health["state"] == "OPERATIVO"
    assert result.records_received == 0
    assert result.records_written == 0
