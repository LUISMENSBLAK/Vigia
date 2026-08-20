from datetime import UTC, datetime

import httpx

from vigia_ai.historical.jcyl import JcylHistoricalClient, build_jcyl_corpus, select_pilot_events
from vigia_ai.historical.models import TimestampPrecision


def record(*, status: str = "ACTIVO", time: str | None = "16:20") -> dict[str, object]:
    return {
        "fecha_de_inicio": "2025-08-16",
        "hora_de_inicio": time,
        "fecha_del_parte": "2025-08-16",
        "hora_del_parte": "17:00",
        "fecha_extinguido": None,
        "hora_extinguido": None,
        "provincia": ["LEÓN", "PALENCIA"],
        "termino_municipal": "CANALEJAS(ALMANZA) - SAN PEDRO DE CANSOLES(GUARDO)",
        "posicion": {"lon": -5.035873, "lat": 42.658876},
        "tipo_y_has_de_superficie_afectada": "ARBOLADO:2.145,29 HA. ;",
        "causa_probable": "DESCONOCIDO",
        "situacion_actual": status,
    }


def test_reference_versions_deduplicate_into_stable_event() -> None:
    now = datetime(2026, 8, 20, tzinfo=UTC)
    events = build_jcyl_corpus(
        [record(status="ACTIVO"), record(status="EXTINGUIDO")], retrieved_at=now
    )
    reversed_events = build_jcyl_corpus(
        [record(status="EXTINGUIDO"), record(status="ACTIVO")], retrieved_at=now
    )
    assert len(events) == 1
    assert len(events[0].references) == 2
    assert events[0].event_id == reversed_events[0].event_id
    assert events[0].maximum_reported_area_ha == 2145.29


def test_date_only_never_invents_noon() -> None:
    event = build_jcyl_corpus(
        [record(time=None)], retrieved_at=datetime(2026, 8, 20, tzinfo=UTC)
    )[0]
    start = event.official_start
    assert start is not None
    assert start.precision is TimestampPrecision.DATE_ONLY
    assert start.instant is None
    assert start.calendar_date is not None


def test_pilot_policy_is_independent_of_engine_outputs() -> None:
    event = build_jcyl_corpus(
        [record()], retrieved_at=datetime(2026, 8, 20, tzinfo=UTC)
    )[0]
    selected = select_pilot_events((event,))
    assert selected == (event,)


async def test_client_follows_only_the_official_download_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "datosabiertos.jcyl.es":
            return httpx.Response(
                302,
                headers={
                    "location": (
                        "https://analisis.datosabiertos.jcyl.es/api/explore/v2.1/"
                        "catalog/datasets/incendios-forestales/exports/json"
                    )
                },
            )
        return httpx.Response(200, json=[record()])

    payload = await JcylHistoricalClient(transport=httpx.MockTransport(handler)).fetch()
    assert isinstance(payload, list)
    assert payload[0]["fecha_de_inicio"] == "2025-08-16"
