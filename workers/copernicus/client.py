import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


class CopernicusError(RuntimeError):
    error_code = "COPERNICUS_ERROR"


class MissingCopernicusCredentialsError(CopernicusError):
    error_code = "MISSING_COPERNICUS_CREDENTIALS"


class CopernicusHTTPError(CopernicusError):
    error_code = "COPERNICUS_HTTP_ERROR"


@dataclass(frozen=True, slots=True)
class AccessToken:
    value: str
    expires_at: float


class CopernicusClient:
    def __init__(
        self,
        client_id: str | None,
        client_secret: str | None,
        *,
        token_url: str,
        base_url: str,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not client_id or not client_secret:
            raise MissingCopernicusCredentialsError(
                "Faltan COPERNICUS_CLIENT_ID y/o COPERNICUS_CLIENT_SECRET."
            )
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport
        self._clock = clock
        self._token: AccessToken | None = None
        self._token_lock = asyncio.Lock()

    async def access_token(self) -> str:
        if self._token is not None and self._token.expires_at > self._clock() + 60:
            return self._token.value
        async with self._token_lock:
            if self._token is not None and self._token.expires_at > self._clock() + 60:
                return self._token.value
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, transport=self._transport, follow_redirects=False
                ) as client:
                    response = await client.post(
                        self._token_url,
                        data={
                            "grant_type": "client_credentials",
                            "client_id": self._client_id,
                            "client_secret": self._client_secret,
                        },
                        headers={"Accept": "application/json"},
                    )
                if not 200 <= response.status_code < 300:
                    raise CopernicusHTTPError(
                        f"Copernicus OAuth respondió con HTTP {response.status_code}."
                    )
                payload = response.json()
                token = payload.get("access_token") if isinstance(payload, dict) else None
                expires_in = payload.get("expires_in") if isinstance(payload, dict) else None
                if not isinstance(token, str) or not isinstance(expires_in, (int, float)):
                    raise CopernicusHTTPError("Copernicus OAuth devolvió un token inválido.")
            except CopernicusError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                raise CopernicusHTTPError("No se pudo completar Copernicus OAuth.") from exc
            self._token = AccessToken(value=token, expires_at=self._clock() + float(expires_in))
            return token

    async def catalog_search(
        self,
        *,
        collection: str,
        bbox: tuple[float, float, float, float],
        start: datetime,
        end: datetime,
        limit: int = 20,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise ValueError("limit debe estar entre 1 y 100.")
        west, south, east, north = bbox
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("bbox no es válido.")
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("La ventana temporal debe ser válida y contener zona horaria.")
        token = await self.access_token()
        payload = {
            "bbox": list(bbox),
            "datetime": f"{start.isoformat()}/{end.isoformat()}",
            "collections": [collection],
            "limit": limit,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as client:
                response = await client.post(
                    f"{self._base_url}/catalog/v1/search",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/geo+json"},
                )
            if not 200 <= response.status_code < 300:
                raise CopernicusHTTPError(
                    f"Copernicus Catalog respondió con HTTP {response.status_code}."
                )
            data = response.json()
            if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
                raise CopernicusHTTPError("Copernicus Catalog devolvió un payload inválido.")
            return data
        except CopernicusError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise CopernicusHTTPError("No se pudo completar Copernicus Catalog.") from exc

    async def process(self, request: dict[str, Any]) -> bytes:
        token = await self.access_token()
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/process",
                    json=request,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "image/tiff",
                    },
                )
            if not 200 <= response.status_code < 300:
                raise CopernicusHTTPError(
                    f"Copernicus Process respondió con HTTP {response.status_code}."
                )
            content_type = response.headers.get("content-type", "").split(";", 1)[0]
            if content_type not in {"image/tiff", "image/x-tiff"} or not response.content:
                raise CopernicusHTTPError("Copernicus Process devolvió un raster inválido.")
            return response.content
        except CopernicusError:
            raise
        except httpx.HTTPError as exc:
            raise CopernicusHTTPError("No se pudo completar Copernicus Process.") from exc


SENTINEL_COLLECTIONS = {
    "sentinel-1": "sentinel-1-grd",
    "sentinel-2": "sentinel-2-l2a",
    "sentinel-3": "sentinel-3-slstr",
}


SENTINEL_2_INDEX_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: ["B04", "B08", "B11", "B12", "SCL", "dataMask"],
    output: { bands: 4, sampleType: "FLOAT32" }
  };
}
function ratio(a, b) { return (a + b) === 0 ? NaN : (a - b) / (a + b); }
function valid(s) {
  return s.dataMask === 1 && ![0, 1, 3, 8, 9, 10, 11].includes(s.SCL);
}
function evaluatePixel(s) {
  if (!valid(s)) return [NaN, NaN, NaN, 0];
  return [ratio(s.B08, s.B04), ratio(s.B08, s.B11), ratio(s.B08, s.B12), 1];
}
"""


def sentinel_2_index_request(
    *,
    bbox: tuple[float, float, float, float],
    start: datetime,
    end: datetime,
    width: int,
    height: int,
) -> dict[str, Any]:
    if width <= 0 or height <= 0 or width * height > 4_000_000:
        raise ValueError("La salida debe ser positiva y no superar cuatro millones de píxeles.")
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("La ventana temporal debe ser válida y contener zona horaria.")
    return {
        "input": {
            "bounds": {
                "bbox": list(bbox),
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {"from": start.isoformat(), "to": end.isoformat()},
                        "mosaickingOrder": "leastCC",
                        "maxCloudCoverage": 30,
                    },
                }
            ],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
        },
        "evalscript": SENTINEL_2_INDEX_EVALSCRIPT,
    }
