import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

import httpx


class FirmsSource(StrEnum):
    VIIRS_NOAA20_NRT = "VIIRS_NOAA20_NRT"
    VIIRS_NOAA21_NRT = "VIIRS_NOAA21_NRT"
    VIIRS_SNPP_NRT = "VIIRS_SNPP_NRT"
    MODIS_NRT = "MODIS_NRT"

    @property
    def catalogue_code(self) -> str:
        return f"NASA_FIRMS_{self.value}"


class FirmsError(RuntimeError):
    error_code = "FIRMS_ERROR"


class MissingFirmsKeyError(FirmsError):
    error_code = "MISSING_NASA_FIRMS_MAP_KEY"


class FirmsTimeoutError(FirmsError):
    error_code = "FIRMS_TIMEOUT"


class FirmsHTTPError(FirmsError):
    error_code = "FIRMS_HTTP_ERROR"


class FirmsQuotaError(FirmsError):
    error_code = "FIRMS_QUOTA"


class FirmsPayloadError(FirmsError):
    error_code = "FIRMS_INVALID_PAYLOAD"


@dataclass(frozen=True, slots=True)
class FirmsObservation:
    external_id: str
    latitude: float
    longitude: float
    acquired_at: datetime
    satellite: str
    instrument: str
    confidence: str | None
    brightness: float | None
    frp: float | None
    daynight: str | None
    source: FirmsSource
    received_at: datetime
    raw_properties: dict[str, str]


def _number(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "").strip()
    return float(value) if value else None


def _first_number(row: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        value = _number(row, key)
        if value is not None:
            return value
    return None


def _external_id(row: dict[str, str], source: FirmsSource) -> str:
    identity = {
        "source": source.value,
        "latitude": row.get("latitude", "").strip(),
        "longitude": row.get("longitude", "").strip(),
        "acq_date": row.get("acq_date", "").strip(),
        "acq_time": row.get("acq_time", "").strip().zfill(4),
        "satellite": row.get("satellite", "").strip(),
        "instrument": row.get("instrument", "").strip(),
    }
    canonical = json.dumps(identity, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def parse_firms_csv(
    payload: str,
    source: FirmsSource,
    *,
    received_at: datetime,
) -> list[FirmsObservation]:
    if received_at.tzinfo is None:
        raise ValueError("received_at debe incluir zona horaria.")
    reader = csv.DictReader(io.StringIO(payload))
    required = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise FirmsPayloadError("La respuesta FIRMS no contiene las columnas obligatorias.")

    observations: list[FirmsObservation] = []
    for line_number, row in enumerate(reader, start=2):
        try:
            acquisition = datetime.strptime(
                f"{row['acq_date']} {row['acq_time'].zfill(4)}", "%Y-%m-%d %H%M"
            ).replace(tzinfo=UTC)
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError("coordenadas fuera de rango")
            if acquisition > received_at:
                raise ValueError("la observación es posterior a su recepción")
            observations.append(
                FirmsObservation(
                    external_id=_external_id(row, source),
                    latitude=latitude,
                    longitude=longitude,
                    acquired_at=acquisition,
                    satellite=row.get("satellite", "").strip(),
                    instrument=row.get("instrument", "").strip(),
                    confidence=row.get("confidence", "").strip() or None,
                    brightness=_first_number(row, "bright_ti4", "brightness"),
                    frp=_number(row, "frp"),
                    daynight=row.get("daynight", "").strip() or None,
                    source=source,
                    received_at=received_at.astimezone(UTC),
                    raw_properties={key: value for key, value in row.items() if key is not None},
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FirmsPayloadError(f"Fila FIRMS inválida en la línea {line_number}.") from exc
    return observations


class FirmsClient:
    base_url = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

    def __init__(
        self,
        map_key: str | None,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not map_key:
            raise MissingFirmsKeyError("Falta la variable obligatoria NASA_FIRMS_MAP_KEY.")
        self._map_key = map_key
        self._timeout = timeout_seconds
        self._transport = transport

    async def fetch_area(
        self,
        source: FirmsSource,
        *,
        bbox: tuple[float, float, float, float] = (-9.5, 35.7, 4.6, 43.9),
        day_range: int = 1,
        end_date: date | None = None,
    ) -> list[FirmsObservation]:
        if day_range not in range(1, 6):
            raise ValueError("day_range debe estar entre 1 y 5.")
        west, south, east, north = bbox
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("bbox no es válido.")
        area = ",".join(str(value) for value in bbox)
        target_date = (end_date or datetime.now(UTC).date()).isoformat()
        url = f"{self.base_url}/{self._map_key}/{source.value}/{area}/{day_range}/{target_date}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.get(url, headers={"Accept": "text/csv"})
        except httpx.TimeoutException as exc:
            raise FirmsTimeoutError("NASA FIRMS no respondió dentro del tiempo límite.") from exc
        except httpx.HTTPError as exc:
            raise FirmsHTTPError("No se pudo completar la llamada a NASA FIRMS.") from exc

        if response.status_code == 429:
            raise FirmsQuotaError("NASA FIRMS rechazó la llamada por cuota.")
        if not 200 <= response.status_code < 300:
            raise FirmsHTTPError(f"NASA FIRMS respondió con HTTP {response.status_code}.")
        normalized = response.text.casefold()
        if "transaction limit" in normalized or "exceeded" in normalized and "quota" in normalized:
            raise FirmsQuotaError("NASA FIRMS indicó que la cuota está agotada.")
        if "invalid map_key" in normalized or "invalid map key" in normalized:
            raise FirmsHTTPError("NASA FIRMS rechazó NASA_FIRMS_MAP_KEY.")
        return parse_firms_csv(response.text, source, received_at=datetime.now(UTC))


def raw_input_hash(observation: FirmsObservation) -> str:
    canonical: dict[str, Any] = {
        "source": observation.source.value,
        "raw_properties": observation.raw_properties,
    }
    serialized = json.dumps(canonical, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()
