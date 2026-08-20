import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx


class EumetsatError(RuntimeError):
    error_code = "EUMETSAT_ERROR"


class MissingEumetsatCredentialsError(EumetsatError):
    error_code = "MISSING_EUMETSAT_CREDENTIALS"


class EumetsatAuthenticationError(EumetsatError):
    error_code = "EUMETSAT_AUTHENTICATION_REJECTED"


class EumetsatHTTPError(EumetsatError):
    error_code = "EUMETSAT_HTTP_ERROR"


class EumetsatPayloadError(EumetsatError):
    error_code = "EUMETSAT_INVALID_PAYLOAD"


@dataclass(frozen=True, slots=True)
class AccessToken:
    value: str
    expires_at: float


class EumetsatClient:
    def __init__(
        self,
        consumer_key: str | None,
        consumer_secret: str | None,
        *,
        base_url: str = "https://api.eumetsat.int",
        timeout_seconds: float = 45.0,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not consumer_key or not consumer_secret:
            raise MissingEumetsatCredentialsError(
                "Faltan EUMETSAT_CONSUMER_KEY y/o EUMETSAT_CONSUMER_SECRET."
            )
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
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
                    timeout=self._timeout,
                    transport=self._transport,
                    follow_redirects=False,
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/token",
                        auth=httpx.BasicAuth(self._consumer_key, self._consumer_secret),
                        data={"grant_type": "client_credentials", "validity_period": 3600},
                        headers={"Accept": "application/json"},
                    )
            except httpx.HTTPError as exc:
                raise EumetsatHTTPError("No se pudo completar EUMETSAT OAuth.") from exc
            if response.status_code in {400, 401, 403}:
                raise EumetsatAuthenticationError(
                    "EUMETSAT_CONSUMER_KEY/EUMETSAT_CONSUMER_SECRET: autenticación rechazada"
                )
            if not 200 <= response.status_code < 300:
                raise EumetsatHTTPError(
                    f"EUMETSAT OAuth respondió con HTTP {response.status_code}."
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise EumetsatPayloadError("EUMETSAT OAuth devolvió JSON inválido.") from exc
            token = payload.get("access_token") if isinstance(payload, dict) else None
            expires_in = payload.get("expires_in") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not isinstance(expires_in, (int, float)):
                raise EumetsatPayloadError("EUMETSAT OAuth devolvió un token inválido.")
            self._token = AccessToken(value=token, expires_at=self._clock() + float(expires_in))
            return token

    async def collection_metadata(self, collection_id: str) -> dict[str, Any]:
        if not collection_id:
            raise ValueError("collection_id es obligatorio.")
        token = await self.access_token()
        endpoint = (
            f"{self._base_url}/data/browse/1.0.0/collections/"
            f"{quote(collection_id, safe='')}"
        )
        payload = await self._get_json(
            endpoint,
            token=token,
            params={"format": "json"},
            operation="catálogo",
        )
        collection = payload.get("collection")
        if not isinstance(collection, dict):
            raise EumetsatPayloadError("EUMETSAT no devolvió metadata de colección válida.")
        return collection

    async def search_products(
        self,
        collection_id: str,
        *,
        start: datetime,
        end: datetime,
        limit: int = 5,
    ) -> dict[str, Any]:
        if not collection_id:
            raise ValueError("collection_id es obligatorio.")
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("La ventana temporal debe ser válida y contener zona horaria.")
        if not 1 <= limit <= 100:
            raise ValueError("limit debe estar entre 1 y 100.")
        token = await self.access_token()
        payload = await self._get_json(
            f"{self._base_url}/data/search-products/1.0.0/os",
            token=token,
            params={
                "format": "json",
                "pi": collection_id,
                "si": 0,
                "c": limit,
                "dtstart": start.isoformat(),
                "dtend": end.isoformat(),
            },
            operation="búsqueda",
        )
        features = payload.get("features")
        total_results = payload.get("totalResults")
        if not isinstance(features, list) or not isinstance(total_results, int):
            raise EumetsatPayloadError("EUMETSAT devolvió resultados de búsqueda inválidos.")
        return payload

    async def _get_json(
        self,
        url: str,
        *,
        token: str,
        params: dict[str, str | int | float | bool | None],
        operation: str,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise EumetsatHTTPError(
                f"No se pudo completar la operación EUMETSAT ({operation})."
            ) from exc
        if response.status_code in {401, 403}:
            raise EumetsatAuthenticationError(
                "EUMETSAT_CONSUMER_KEY/EUMETSAT_CONSUMER_SECRET: autenticación rechazada"
            )
        if not 200 <= response.status_code < 300:
            raise EumetsatHTTPError(
                f"EUMETSAT {operation} respondió con HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise EumetsatPayloadError(
                f"EUMETSAT {operation} devolvió JSON inválido."
            ) from exc
        if not isinstance(payload, dict):
            raise EumetsatPayloadError(
                f"EUMETSAT {operation} devolvió un payload inválido."
            )
        return payload


class EumetsatDiscoveryClient:
    """Anonymous catalogue access; product download still requires OAuth."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.eumetsat.int",
        timeout_seconds: float = 45.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    async def collection_metadata(self, collection_id: str) -> dict[str, Any]:
        payload = await self._get_json(
            f"{self._base_url}/data/browse/1.0.0/collections/{quote(collection_id, safe='')}",
            params={"format": "json"},
            operation="catálogo anónimo",
        )
        collection = payload.get("collection")
        if not isinstance(collection, dict):
            raise EumetsatPayloadError("EUMETSAT no devolvió metadata de colección válida.")
        return collection

    async def search_products(
        self,
        collection_id: str,
        *,
        start: datetime,
        end: datetime,
        limit: int = 5,
    ) -> dict[str, Any]:
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("La ventana temporal debe ser válida y contener zona horaria.")
        if not 1 <= limit <= 100:
            raise ValueError("limit debe estar entre 1 y 100.")
        payload = await self._get_json(
            f"{self._base_url}/data/search-products/1.0.0/os",
            params={
                "format": "json",
                "pi": collection_id,
                "si": 0,
                "c": limit,
                "dtstart": start.isoformat(),
                "dtend": end.isoformat(),
            },
            operation="búsqueda anónima",
        )
        if not isinstance(payload.get("features"), list) or not isinstance(
            payload.get("totalResults"), int
        ):
            raise EumetsatPayloadError("EUMETSAT devolvió resultados de búsqueda inválidos.")
        return payload

    async def _get_json(
        self,
        url: str,
        *,
        params: dict[str, str | int | float | bool | None],
        operation: str,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.get(
                    url, params=params, headers={"Accept": "application/json"}
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EumetsatHTTPError(
                f"No se pudo completar EUMETSAT ({operation})."
            ) from exc
        if not isinstance(payload, dict):
            raise EumetsatPayloadError(
                f"EUMETSAT {operation} devolvió un payload inválido."
            )
        return payload
