from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest

from workers.aemet.client import (
    AemetClient,
    AemetPayloadError,
    MissingAemetKeyError,
    parse_aemet_observations,
)
from workers.aemet.repository import AemetIngestRun, AemetRepository


def test_missing_aemet_key_is_explicit() -> None:
    with pytest.raises(MissingAemetKeyError, match="AEMET_API_KEY"):
        AemetClient(None)


def test_parses_only_observed_station_values() -> None:
    received_at = datetime(2026, 8, 16, 12, 5, tzinfo=UTC)
    observations = parse_aemet_observations(
        [
            {
                "idema": "2444",
                "ubi": "ÁVILA",
                "lat": 40.65,
                "lon": -4.68,
                "fint": "2026-08-16T12:00:00+00:00",
                "ta": 27.4,
                "hr": 31.0,
                "vv": 4.2,
                "dv": 245.0,
                "vmax": 7.1,
                "prec": 0.0,
                "pres": 923.2,
            }
        ],
        received_at=received_at,
    )
    observation = observations[0]
    assert observation.value_type == "OBSERVADO"
    assert len(observation.external_id) == 64
    assert observation.observed_at == datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    assert observation.temperature_c == 27.4
    assert observation.raw_properties["idema"] == "2444"
    assert observation.quality["qualification"] == "automatic_controls_only"


def test_rejects_forecast_shaped_or_incomplete_data() -> None:
    with pytest.raises(AemetPayloadError):
        parse_aemet_observations([{"idema": "2444"}], received_at=datetime.now(UTC))


async def test_rejects_untrusted_data_url() -> None:
    def locator(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"estado": 200, "datos": "https://example.com/data"})

    client = AemetClient("test-key", transport=httpx.MockTransport(locator))
    with pytest.raises(AemetPayloadError, match="no autorizada"):
        await client.fetch_observations()


async def test_accepts_official_iso_8859_1_payload() -> None:
    payload = """[{"idema":"2444","ubi":"ÁVILA","lat":40.65,"lon":-4.68,
      "fint":"2026-08-16T12:00:00+00:00","ta":27.4}]""".encode("iso-8859-1")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/todas"):
            return httpx.Response(
                200,
                json={"estado": 200, "datos": "https://opendata.aemet.es/data"},
            )
        return httpx.Response(200, content=payload, headers={"content-type": "text/plain"})

    observations = await AemetClient(
        "test-key", transport=httpx.MockTransport(handler)
    ).fetch_observations()
    assert len(observations) == 1
    assert observations[0].station_name == "ÁVILA"


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


async def test_successful_empty_aemet_check_is_operational() -> None:
    database = RecordingDatabase()
    repository = AemetRepository(database)  # type: ignore[arg-type]
    now = datetime.now(UTC)
    run = AemetIngestRun(id=uuid4(), source_id=uuid4())
    written = await repository.persist(run, [], code_commit="test", finished_at=now)
    health = next(item for item in database.connection.parameters if "health_state" in item)
    assert health["health_state"] == "OPERATIVO"
    assert written == 0
