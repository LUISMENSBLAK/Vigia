import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

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


@dataclass(frozen=True, slots=True)
class AemetHourlyForecast:
    municipality_code: str
    issued_at: datetime
    valid_at: datetime
    latitude: float
    longitude: float
    model_name: str
    model_run: str
    variables: dict[str, Any]
    quality: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AemetDailyClimate:
    station_code: str
    station_name: str
    province: str
    calendar_date: date
    temperature_mean_c: float | None
    temperature_min_c: float | None
    temperature_max_c: float | None
    relative_humidity_mean_pct: float | None
    wind_speed_mean_ms: float | None
    gust_ms: float | None
    precipitation_24h_mm: float | None
    quality: dict[str, Any]
    raw_properties: dict[str, Any]


def _number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None or value == "":
        return None
    return float(value)


def _locale_number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def parse_aemet_daily_climate(payload: object) -> list[AemetDailyClimate]:
    if not isinstance(payload, list):
        raise AemetPayloadError("La climatología diaria AEMET no es una lista.")
    output: list[AemetDailyClimate] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise AemetPayloadError(f"Registro climatológico inválido en {index}.")
        row = {str(key): value for key, value in item.items()}
        try:
            calendar_date = date.fromisoformat(str(row["fecha"]))
            station_code = str(row["indicativo"]).strip()
            station_name = str(row["nombre"]).strip()
            province = str(row["provincia"]).strip()
            if not station_code:
                raise ValueError("indicativo vacío")
        except (KeyError, ValueError) as exc:
            raise AemetPayloadError(f"Registro climatológico inválido en {index}.") from exc
        output.append(
            AemetDailyClimate(
                station_code=station_code,
                station_name=station_name,
                province=province,
                calendar_date=calendar_date,
                temperature_mean_c=_locale_number(row, "tmed"),
                temperature_min_c=_locale_number(row, "tmin"),
                temperature_max_c=_locale_number(row, "tmax"),
                relative_humidity_mean_pct=_locale_number(row, "hrMedia"),
                wind_speed_mean_ms=_locale_number(row, "velmedia"),
                gust_ms=_locale_number(row, "racha"),
                precipitation_24h_mm=_locale_number(row, "prec"),
                quality={
                    "temporal_precision": "DATE_ONLY",
                    "fwi_compatible": False,
                    "fwi_reason": "DAILY_MEANS_DO_NOT_REPLACE_NOON_LOCAL_STANDARD_OBSERVATIONS",
                    "precipitation_trace_raw": row.get("prec")
                    if _locale_number(row, "prec") is None
                    else None,
                },
                raw_properties=row,
            )
        )
    return output


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


def _period_values(items: object) -> dict[str, object]:
    if not isinstance(items, list):
        return {}
    output: dict[str, object] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("periodo"), str):
            output[item["periodo"]] = item.get("value")
    return output


def _interval_value(items: object, hour: int) -> object | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("periodo"), str):
            continue
        period = item["periodo"]
        if len(period) == 2 and period.isdigit() and int(period) == hour:
            return item.get("value")
        if len(period) == 4 and period.isdigit():
            start, end = int(period[:2]), int(period[2:])
            if start <= hour < end:
                return item.get("value")
    return None


def _wind_values(items: object) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    speed: dict[str, object] = {}
    direction: dict[str, object] = {}
    gust: dict[str, object] = {}
    if not isinstance(items, list):
        return speed, direction, gust
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("periodo"), str):
            continue
        period = item["periodo"]
        if isinstance(item.get("velocidad"), list) and item["velocidad"]:
            speed[period] = item["velocidad"][0]
        if isinstance(item.get("direccion"), list) and item["direccion"]:
            direction[period] = item["direccion"][0]
        if item.get("value") not in {None, ""}:
            gust[period] = item["value"]
    return speed, direction, gust


def parse_aemet_hourly_forecasts(
    payload: object,
    *,
    municipality_code: str,
    latitude: float,
    longitude: float,
) -> list[AemetHourlyForecast]:
    """Normaliza el producto horario sin convertir probabilidad de lluvia en precipitación."""
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise AemetPayloadError("La predicción horaria AEMET no tiene el formato esperado.")
    document = {str(key): value for key, value in payload[0].items()}
    try:
        issued_raw = document["elaborado"]
        if not isinstance(issued_raw, str):
            raise ValueError("elaborado ausente")
        issued_at = datetime.fromisoformat(issued_raw.replace("Z", "+00:00"))
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=ZoneInfo("Europe/Madrid"))
        issued_at = issued_at.astimezone(UTC)
        prediction = document["prediccion"]
        if not isinstance(prediction, dict) or not isinstance(prediction.get("dia"), list):
            raise ValueError("predicción sin días")
    except (KeyError, TypeError, ValueError) as exc:
        raise AemetPayloadError("La predicción horaria AEMET carece de metadatos.") from exc

    timezone = ZoneInfo("Europe/Madrid")
    output: list[AemetHourlyForecast] = []
    for day in prediction["dia"]:
        if not isinstance(day, dict) or not isinstance(day.get("fecha"), str):
            raise AemetPayloadError("Día horario AEMET inválido.")
        temperature = _period_values(day.get("temperatura"))
        humidity = _period_values(day.get("humedadRelativa"))
        precipitation = _period_values(day.get("precipitacion"))
        sky = _period_values(day.get("estadoCielo"))
        wind_speed, wind_direction, gust = _wind_values(day.get("vientoAndRachaMax"))
        periods = sorted(
            period
            for period in set(temperature)
            | set(humidity)
            | set(precipitation)
            | set(sky)
            | set(wind_speed)
            | set(gust)
            if len(period) == 2
        )
        for period in periods:
            if not period.isdigit() or len(period) not in {2, 4}:
                continue
            hour = int(period[:2])
            local_midnight = datetime.fromisoformat(day["fecha"]).replace(tzinfo=timezone)
            valid_at = local_midnight.replace(hour=hour).astimezone(UTC)
            variables: dict[str, Any] = {
                "temperature_c": temperature.get(period),
                "relative_humidity_pct": humidity.get(period),
                "wind_speed_kmh": wind_speed.get(period),
                "wind_direction_cardinal": wind_direction.get(period),
                "gust_kmh": gust.get(period),
                "precipitation_probability_pct": _interval_value(
                    day.get("probPrecipitacion"), hour
                ),
                "precipitation_mm": precipitation.get(period),
                "sky_state": sky.get(period),
                "raw_day": day,
            }
            output.append(
                AemetHourlyForecast(
                    municipality_code=municipality_code,
                    issued_at=issued_at,
                    valid_at=valid_at,
                    latitude=latitude,
                    longitude=longitude,
                    model_name="AEMET_MUNICIPAL_HOURLY",
                    model_run=issued_at.isoformat(),
                    variables=variables,
                    quality={
                        "value_type": "PRONOSTICADO",
                        "spatial_support": "municipality_reference_point",
                        "precipitation_amount": "AVAILABLE_HOURLY_WHEN_NON_NULL",
                        "fwi_compatible": False,
                        "fwi_reason": "REQUIRES_24H_AGGREGATION_AND_PREVIOUS_DAILY_STATE",
                    },
                )
            )
    return output


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

    async def fetch_hourly_forecasts(
        self, *, municipality_code: str, latitude: float, longitude: float
    ) -> list[AemetHourlyForecast]:
        url = (
            "https://opendata.aemet.es/opendata/api/prediccion/"
            f"especifica/municipio/horaria/{municipality_code}"
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as client:
                locator = await client.get(
                    url,
                    params={"api_key": self._api_key},
                    headers={"Accept": "application/json"},
                )
                if not 200 <= locator.status_code < 300:
                    raise AemetHTTPError(f"AEMET respondió con HTTP {locator.status_code}.")
                envelope = locator.json()
                if not isinstance(envelope, dict) or not isinstance(envelope.get("datos"), str):
                    raise AemetPayloadError("AEMET no devolvió una URL de forecast válida.")
                data_url = envelope["datos"]
                if urlparse(data_url).hostname != "opendata.aemet.es":
                    raise AemetPayloadError("AEMET devolvió una URL de datos no autorizada.")
                response = await client.get(data_url, headers={"Accept": "application/json"})
                if not 200 <= response.status_code < 300:
                    raise AemetHTTPError(
                        f"AEMET forecast respondió con HTTP {response.status_code}."
                    )
                try:
                    payload = response.json()
                except ValueError:
                    try:
                        payload = json.loads(response.content.decode("iso-8859-1"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as fallback_exc:
                        raise AemetPayloadError(
                            "AEMET forecast no devolvió JSON válido."
                        ) from fallback_exc
        except httpx.TimeoutException as exc:
            raise AemetTimeoutError("AEMET no respondió dentro del tiempo límite.") from exc
        except AemetError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise AemetHTTPError("No se pudo completar la llamada de forecast AEMET.") from exc
        return parse_aemet_hourly_forecasts(
            payload,
            municipality_code=municipality_code,
            latitude=latitude,
            longitude=longitude,
        )

    async def fetch_daily_climate(
        self, *, start_date: date, end_date: date
    ) -> list[AemetDailyClimate]:
        if end_date < start_date or (end_date - start_date).days > 31:
            raise ValueError("La ventana climatológica debe estar entre 1 y 32 días.")
        start = f"{start_date.isoformat()}T00:00:00UTC"
        end = f"{end_date.isoformat()}T23:59:59UTC"
        url = (
            "https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos/"
            f"fechaini/{start}/fechafin/{end}/todasestaciones"
        )
        try:
            async with httpx.AsyncClient(
                timeout=max(self._timeout, 90),
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                locator = await client.get(
                    url,
                    params={"api_key": self._api_key},
                    headers={"Accept": "application/json"},
                )
                if not 200 <= locator.status_code < 300:
                    raise AemetHTTPError(f"AEMET respondió con HTTP {locator.status_code}.")
                envelope = locator.json()
                if not isinstance(envelope, dict) or not isinstance(envelope.get("datos"), str):
                    raise AemetPayloadError("AEMET no devolvió una URL climatológica válida.")
                data_url = envelope["datos"]
                if urlparse(data_url).hostname != "opendata.aemet.es":
                    raise AemetPayloadError("AEMET devolvió una URL de datos no autorizada.")
                response = await client.get(data_url, headers={"Accept": "application/json"})
                if not 200 <= response.status_code < 300:
                    raise AemetHTTPError(
                        f"AEMET climatología respondió con HTTP {response.status_code}."
                    )
        except httpx.TimeoutException as exc:
            raise AemetTimeoutError("AEMET no respondió dentro del tiempo límite.") from exc
        try:
            payload = response.json()
        except ValueError:
            try:
                payload = json.loads(response.content.decode("iso-8859-1"))
            except (UnicodeDecodeError, json.JSONDecodeError) as fallback_exc:
                raise AemetPayloadError(
                    "AEMET climatología no devolvió JSON válido."
                ) from fallback_exc
        return parse_aemet_daily_climate(payload)
