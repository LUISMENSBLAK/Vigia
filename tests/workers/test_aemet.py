from datetime import UTC, datetime

import httpx
import pytest

from workers.aemet.client import (
    AemetClient,
    AemetPayloadError,
    MissingAemetKeyError,
    parse_aemet_observations,
)


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
