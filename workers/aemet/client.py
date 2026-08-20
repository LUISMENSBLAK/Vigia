import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx


class AemetError(RuntimeError):
    error_code = "AEMET_ERROR"


class MissingAemetKeyError(AemetError):
    error_code = "MISSING_AEMET_API_KEY"


class AemetTimeoutError(AemetError):
    error_code = "AEMET_TIMEOUT"


class AemetHTTPError(AemetError):
    error_code = "AEMET_HTTP_ERROR"


class AemetPayloadError(AemetError):
    error_code = "AEMET_INVALID_PAYLOAD"


@dataclass(frozen=True, slots=True)
class AemetObservation:
    external_id: str
    station_code: str
    station_name: str | None
    latitude: float
    longitude: float
    observed_at: datetime
    received_at: datetime
    value_type: str
    temperature_c: float | None
    relative_humidity_pct: float | None
    wind_speed_ms: float | None
    wind_direction_deg: float | None
    gust_ms: float | None
    precipitation_mm: float | None
    pressure_hpa: float | None
    quality: dict[str, Any]
    raw_properties: dict[str, Any]


def _number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None or value == "":
        return None
    return float(value)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp ausente")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp sin zona horaria")
    return parsed.astimezone(UTC)


def parse_aemet_observations(
    payload: object,
    *,
    received_at: datetime,
) -> list[AemetObservation]:
    if not isinstance(payload, list):
        raise AemetPayloadError("La respuesta de datos AEMET no es una lista.")
    observations: list[AemetObservation] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise AemetPayloadError(f"Registro AEMET inválido en la posición {index}.")
        row = {str(key): value for key, value in item.items()}
        try:
            observed_at = _timestamp(row.get("fint"))
            latitude = float(row["lat"])
            longitude = float(row["lon"])
            station_code = str(row["idema"]).strip()
            if not station_code or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError("identidad o coordenadas inválidas")
            if observed_at > received_at:
                raise ValueError("observación posterior a recepción")
            observations.append(
                AemetObservation(
                    external_id=hashlib.sha256(
                        f"AEMET_OPEN_DATA:{station_code}:{observed_at.isoformat()}".encode()
                    ).hexdigest(),
                    station_code=station_code,
                    station_name=str(row["ubi"]).strip() if row.get("ubi") else None,
                    latitude=latitude,
                    longitude=longitude,
                    observed_at=observed_at,
                    received_at=received_at.astimezone(UTC),
                    value_type="OBSERVADO",
                    temperature_c=_number(row, "ta"),
                    relative_humidity_pct=_number(row, "hr"),
                    wind_speed_ms=_number(row, "vv"),
                    wind_direction_deg=_number(row, "dv"),
                    gust_ms=_number(row, "vmax"),
                    precipitation_mm=_number(row, "prec"),
                    pressure_hpa=_number(row, "pres"),
                    quality={
                        "provider_quality": row.get("calidad"),
                        "qualification": "automatic_controls_only",
                    },
                    raw_properties=row,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AemetPayloadError(f"Registro AEMET inválido en la posición {index}.") from exc
    return observations


class AemetClient:
    observations_url = "https://opendata.aemet.es/opendata/api/observacion/convencional/todas"

    def __init__(
        self,
        api_key: str | None,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise MissingAemetKeyError("Falta la variable obligatoria AEMET_API_KEY.")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._transport = transport

    async def fetch_observations(self) -> list[AemetObservation]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as client:
                locator = await client.get(
                    self.observations_url,
                    params={"api_key": self._api_key},
                    headers={"Accept": "application/json"},
                )
                if not 200 <= locator.status_code < 300:
                    raise AemetHTTPError(f"AEMET respondió con HTTP {locator.status_code}.")
                envelope = locator.json()
                if not isinstance(envelope, dict) or not isinstance(envelope.get("datos"), str):
                    raise AemetPayloadError("AEMET no devolvió una URL de datos válida.")
                data_url = envelope["datos"]
                if urlparse(data_url).hostname != "opendata.aemet.es":
                    raise AemetPayloadError("AEMET devolvió una URL de datos no autorizada.")
                response = await client.get(data_url, headers={"Accept": "application/json"})
                if not 200 <= response.status_code < 300:
                    raise AemetHTTPError(f"AEMET datos respondió con HTTP {response.status_code}.")
        except httpx.TimeoutException as exc:
            raise AemetTimeoutError("AEMET no respondió dentro del tiempo límite.") from exc
        except AemetError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise AemetHTTPError("No se pudo completar la llamada a AEMET.") from exc
        try:
            payload = response.json()
        except ValueError:
            try:
                payload = json.loads(response.content.decode("iso-8859-1"))
            except (UnicodeDecodeError, json.JSONDecodeError) as fallback_exc:
                raise AemetPayloadError(
                    "AEMET devolvió datos que no son JSON válido."
                ) from fallback_exc
        return parse_aemet_observations(payload, received_at=datetime.now(UTC))
