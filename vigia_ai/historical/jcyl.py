from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx

from .models import (
    HistoricalFireEvent,
    HistoricalFireReference,
    HistoricalTimestamp,
    ReferenceQuality,
    TimestampPrecision,
)

JCYL_DATASET_URL = (
    "https://datosabiertos.jcyl.es/web/jcyl/risp/es/medio-ambiente/"
    "incendios_forestales/1284333417830.json"
)
JCYL_CATALOG_URL = (
    "https://datosabiertos.jcyl.es/web/jcyl/set/es/medio-ambiente/"
    "incendios_forestales/1284333417830"
)
PROVIDER = "Junta de Castilla y León"
DATASET = "Incendios forestales"
REGION = "Castilla y León"
LOCAL_TIMEZONE = ZoneInfo("Europe/Madrid")
ALLOWED_DOWNLOAD_HOSTS = {
    "datosabiertos.jcyl.es",
    "analisis.datosabiertos.jcyl.es",
}


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "-", normalized.upper()).strip("-")


def _provinces(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, list):
        candidates = [str(item) for item in value]
    else:
        return ()
    return tuple(
        sorted(
            {
                province.strip()
                for candidate in candidates
                for province in candidate.split(",")
                if province.strip()
            }
        )
    )


def _area_ha(value: object) -> float | None:
    matches = re.findall(r"(\d[\d.,]*)\s*HA", str(value).upper())
    values: list[float] = []
    for match in matches:
        try:
            normalized = (
                match.replace(".", "").replace(",", ".")
                if "," in match
                else match
            )
            values.append(float(normalized))
        except ValueError:
            continue
    return sum(values) if values else None


def _timestamp(
    row: dict[str, Any],
    *,
    date_field: str,
    time_field: str,
    meaning: str,
) -> HistoricalTimestamp:
    raw_date = row.get(date_field)
    raw_time = row.get(time_field)
    if not isinstance(raw_date, str) or not raw_date.strip():
        return HistoricalTimestamp(
            meaning=meaning,
            precision=TimestampPrecision.UNKNOWN,
            source=DATASET,
        )
    parsed_date = date.fromisoformat(raw_date.strip())
    if not isinstance(raw_time, str) or not raw_time.strip():
        return HistoricalTimestamp(
            meaning=meaning,
            calendar_date=parsed_date,
            precision=TimestampPrecision.DATE_ONLY,
            source=DATASET,
            timezone="Europe/Madrid",
        )
    pieces = raw_time.strip().split(":")
    if len(pieces) not in {2, 3}:
        raise ValueError(f"Hora histórica no reconocida: {raw_time!r}")
    hour, minute = int(pieces[0]), int(pieces[1])
    second = int(pieces[2]) if len(pieces) == 3 else 0
    local = datetime.combine(parsed_date, datetime.min.time()).replace(
        hour=hour, minute=minute, second=second, tzinfo=LOCAL_TIMEZONE
    )
    return HistoricalTimestamp(
        meaning=meaning,
        instant=local.astimezone(UTC),
        precision=(TimestampPrecision.EXACT if len(pieces) == 3 else TimestampPrecision.MINUTE),
        source=DATASET,
        timezone="Europe/Madrid",
        quality={"original_date": raw_date, "original_time": raw_time},
    )


def _identity(row: dict[str, Any]) -> dict[str, Any]:
    raw_position = row.get("posicion")
    position: dict[str, Any] = raw_position if isinstance(raw_position, dict) else {}
    return {
        "provider": PROVIDER,
        "date": row.get("fecha_de_inicio"),
        "time": row.get("hora_de_inicio"),
        "municipality": row.get("termino_municipal"),
        "longitude": position.get("lon"),
        "latitude": position.get("lat"),
    }


def parse_jcyl_reference(
    raw: object, *, retrieved_at: datetime
) -> tuple[str, HistoricalFireReference]:
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at requiere zona horaria")
    if not isinstance(raw, dict):
        raise ValueError("El registro histórico debe ser un objeto")
    row = {str(key): value for key, value in raw.items()}
    identity = _identity(row)
    event_key = _digest(identity)
    checksum = _digest(row)
    raw_position = row.get("posicion")
    position: dict[str, Any] = raw_position if isinstance(raw_position, dict) else {}
    longitude = position.get("lon")
    latitude = position.get("lat")
    timestamps = tuple(
        stamp
        for stamp in (
            _timestamp(
                row,
                date_field="fecha_de_inicio",
                time_field="hora_de_inicio",
                meaning="official_start_time",
            ),
            _timestamp(
                row,
                date_field="fecha_del_parte",
                time_field="hora_del_parte",
                meaning="reported_time",
            ),
            _timestamp(
                row,
                date_field="fecha_extinguido",
                time_field="hora_extinguido",
                meaning="extinguished_time",
            ),
        )
        if stamp.precision is not TimestampPrecision.UNKNOWN
    )
    quality = (
        ReferenceQuality.HIGH
        if longitude is not None
        and latitude is not None
        and any(
            item.meaning == "official_start_time"
            and item.precision in {TimestampPrecision.MINUTE, TimestampPrecision.EXACT}
            for item in timestamps
        )
        else ReferenceQuality.MEDIUM
        if row.get("fecha_de_inicio")
        else ReferenceQuality.LOW
    )
    reference = HistoricalFireReference(
        reference_id=f"jcyl-{checksum}",
        provider=PROVIDER,
        dataset=DATASET,
        record_id=checksum,
        source_uri=JCYL_DATASET_URL,
        retrieved_at=retrieved_at.astimezone(UTC),
        checksum_sha256=checksum,
        license_uri=None,
        province=_provinces(row.get("provincia")),
        municipality=str(row["termino_municipal"]).strip()
        if row.get("termino_municipal")
        else None,
        region=REGION,
        longitude=float(longitude) if longitude is not None else None,
        latitude=float(latitude) if latitude is not None else None,
        area_ha=_area_ha(row.get("tipo_y_has_de_superficie_afectada")),
        cause=str(row["causa_probable"]).strip() if row.get("causa_probable") else None,
        official_status=str(row["situacion_actual"]).strip()
        if row.get("situacion_actual")
        else None,
        quality=quality,
        timestamps=timestamps,
        original=row,
    )
    return event_key, reference


def build_jcyl_corpus(
    payload: object, *, retrieved_at: datetime
) -> tuple[HistoricalFireEvent, ...]:
    if not isinstance(payload, list):
        raise ValueError("El dataset histórico de Castilla y León no es una lista")
    grouped: dict[str, dict[str, HistoricalFireReference]] = defaultdict(dict)
    for raw in payload:
        event_key, reference = parse_jcyl_reference(raw, retrieved_at=retrieved_at)
        grouped[event_key][reference.reference_id] = reference
    events: list[HistoricalFireEvent] = []
    for event_key, unique_references in grouped.items():
        references = tuple(
            sorted(unique_references.values(), key=lambda item: item.reference_id)
        )
        canonical = references[0]
        date_label = next(
            (
                (stamp.instant.date() if stamp.instant else stamp.calendar_date)
                for stamp in canonical.timestamps
                if stamp.meaning == "official_start_time"
            ),
            None,
        )
        label = "-".join(
            part
            for part in (
                "VIGIA-HIST-ES",
                date_label.isoformat() if date_label else "UNKNOWN-DATE",
                _slug(canonical.municipality or "UNKNOWN-LOCATION")[:48],
                event_key[:10].upper(),
            )
            if part
        )
        events.append(
            HistoricalFireEvent(
                event_id=event_key,
                event_key=event_key,
                vigia_code=label,
                name=canonical.municipality,
                province=canonical.province,
                municipality=canonical.municipality,
                region=canonical.region,
                longitude=canonical.longitude,
                latitude=canonical.latitude,
                reference_quality=max(
                    (item.quality for item in references),
                    key=lambda value: {
                        ReferenceQuality.UNKNOWN: 0,
                        ReferenceQuality.LOW: 1,
                        ReferenceQuality.MEDIUM: 2,
                        ReferenceQuality.HIGH: 3,
                    }[value],
                ),
                references=references,
            )
        )
    return tuple(sorted(events, key=lambda item: item.event_key))


def select_pilot_events(
    events: tuple[HistoricalFireEvent, ...], *, limit: int = 12
) -> tuple[HistoricalFireEvent, ...]:
    """Predeclared engineering policy; never inspects VIGÍA replay outcomes."""
    eligible = [
        event
        for event in events
        if event.reference_quality is ReferenceQuality.HIGH
        and event.longitude is not None
        and event.latitude is not None
        and event.official_start is not None
        and event.official_start.instant is not None
        and event.maximum_reported_area_ha is not None
        and event.maximum_reported_area_ha >= 50.0
    ]
    best_by_stratum: dict[tuple[int, str], HistoricalFireEvent] = {}
    for event in eligible:
        start = event.official_start
        assert start is not None and start.instant is not None
        province = event.province[0] if event.province else "UNKNOWN"
        key = (start.instant.year, province)
        previous = best_by_stratum.get(key)
        if previous is None or (
            event.maximum_reported_area_ha or 0,
            event.event_key,
        ) > (previous.maximum_reported_area_ha or 0, previous.event_key):
            best_by_stratum[key] = event
    return tuple(
        sorted(
            best_by_stratum.values(),
            key=lambda item: (
                -(item.maximum_reported_area_ha or 0),
                item.event_key,
            ),
        )[:limit]
    )


class JcylHistoricalClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 90.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._transport = transport

    async def fetch(self) -> object:
        async with httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=False,
        ) as client:
            response = await client.get(JCYL_DATASET_URL, headers={"Accept": "application/json"})
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    response.raise_for_status()
                redirect_url = urljoin(JCYL_DATASET_URL, location)
                if urlparse(redirect_url).hostname not in ALLOWED_DOWNLOAD_HOSTS:
                    raise ValueError(
                        "Redirección histórica fuera de los hosts oficiales permitidos"
                    )
                response = await client.get(
                    redirect_url, headers={"Accept": "application/json"}
                )
        response.raise_for_status()
        return response.json()
