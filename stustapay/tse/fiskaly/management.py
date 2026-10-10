"""Client for fiskaly's HUB Management API."""

import asyncio
import time
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp

from .client import FiskalyError, FiskalyHTTPError, FiskalyTransportError
from .config import FiskalyManagementCredentials

BASE_URL = "https://dashboard.fiskaly.com/api/v0"
_PAGE_SIZE_ORGANIZATIONS = 5000
_PAGE_SIZE_KEYS = 100
_MAX_PAGES = 1000


class FiskalyManagementClient:
    """Bounded transport and operations for the fiskaly Management API v0."""

    def __init__(self, config: FiskalyManagementCredentials):
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._token: str | None = None
        self._expires_at = 0.0
        self._auth_lock = asyncio.Lock()
        self._requests = asyncio.Semaphore(config.max_concurrency)

    async def __aenter__(self):
        if self._session is not None:
            raise FiskalyError("Fiskaly Management client is already open")
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.request_timeout),
            connector=aiohttp.TCPConnector(limit=self.config.max_concurrency),
        )
        return self

    async def __aexit__(self, *_):
        assert self._session is not None
        await self._session.close()
        self._session = None
        self._token = None
        self._expires_at = 0.0

    async def _send(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        payload: dict[str, Any] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any]:
        if self._session is None:
            raise FiskalyError("Fiskaly Management client is not open")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        url = f"{BASE_URL}/{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        try:
            async with self._requests:
                async with self._session.request(
                    method,
                    url,
                    json=payload,
                    headers=headers,
                    allow_redirects=False,
                ) as response:
                    if not 200 <= response.status < 300:
                        raise FiskalyHTTPError(response.status)
                    data = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise FiskalyTransportError("Fiskaly Management request failed; remote result may be unknown") from None
        except ValueError:
            raise FiskalyError("Fiskaly Management API returned invalid JSON") from None
        if not isinstance(data, dict):
            raise FiskalyError("Fiskaly Management API returned an invalid response object")
        return data

    async def _authenticate(self, rejected_token: str | None = None) -> str:
        async with self._auth_lock:
            if self._token and time.monotonic() < self._expires_at and self._token != rejected_token:
                return self._token
            data = await self._send(
                "POST",
                "auth",
                payload={
                    "api_key": self.config.api_key.get_secret_value(),
                    "api_secret": self.config.api_secret.get_secret_value(),
                },
            )
            token = data.get("access_token")
            if not isinstance(token, str) or not token:
                raise FiskalyError("Fiskaly Management authentication response has no access token")
            claims = data.get("access_token_claims")
            if (
                not isinstance(claims, dict)
                or claims.get("env") != self.config.environment
                or str(claims.get("organization_id")) != str(self.config.group_id)
            ):
                raise FiskalyError("Fiskaly Management credential organization or environment does not match")
            expires_in = data.get("access_token_expires_in", 300)
            if not isinstance(expires_in, (int, float)) or expires_in <= 0:
                raise FiskalyError("Fiskaly Management authentication response has invalid token expiry")
            self._token = token
            self._expires_at = time.monotonic() + max(0, expires_in - 15)
            return token

    async def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any]:
        token = await self._authenticate()
        try:
            return await self._send(method, path, token=token, payload=payload, params=params)
        except FiskalyHTTPError as exc:
            # Never replay a write. A GET can be safely repeated after refreshing auth.
            if exc.status != 401 or method.upper() != "GET":
                raise
        token = await self._authenticate(rejected_token=token)
        return await self._send(method, path, token=token, payload=payload, params=params)

    @staticmethod
    def _identifier(value: Any) -> str:
        return quote(str(value), safe="-")

    async def get_organization(self, org_id: Any) -> dict[str, Any]:
        return await self.request("GET", f"organizations/{self._identifier(org_id)}")

    async def _list(
        self,
        path: str,
        *,
        page_size: int,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        offset = 0
        result: list[dict[str, Any]] = []
        for _ in range(_MAX_PAGES):
            page = await self.request("GET", path, params={**(filters or {}), "limit": page_size, "offset": offset})
            data = page.get("data")
            count = page.get("count")
            if not isinstance(data, list) or not isinstance(count, int) or count < 0:
                raise FiskalyError("Fiskaly Management list response has an invalid shape")
            if not all(isinstance(item, dict) for item in data):
                raise FiskalyError("Fiskaly Management list response contains an invalid item")
            if len(data) > page_size:
                raise FiskalyError("Fiskaly Management list response exceeds requested page size")
            result.extend(data)
            if len(result) >= count or len(data) < page_size:
                return result
            if not data:
                return result
            offset += len(data)
        raise FiskalyError("Fiskaly Management pagination exceeded its safety limit")

    async def list_organizations(self) -> list[dict[str, Any]]:
        return await self._list(
            "organizations",
            page_size=_PAGE_SIZE_ORGANIZATIONS,
            # Include all environments so a retry can reconcile a managed unit
            # that was already created before the requested environment was enabled.
            filters={"managed_by_organization_id": str(self.config.group_id)},
        )

    async def create_organization(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "organizations", payload=payload)

    async def enable_environment(self, org_id: Any) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"organizations/{self._identifier(org_id)}/enable-env",
            payload={"env": self.config.environment},
        )

    async def list_keys(self, org_id: Any) -> list[dict[str, Any]]:
        return await self._list(
            f"organizations/{self._identifier(org_id)}/api-keys",
            page_size=_PAGE_SIZE_KEYS,
        )

    async def create_key(self, org_id: Any, name: str, metadata: dict[str, str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name, "status": "enabled"}
        if metadata is not None:
            payload["metadata"] = metadata
        return await self.request("POST", f"organizations/{self._identifier(org_id)}/api-keys", payload=payload)

    async def disable_key(self, org_id: Any, key_id: Any) -> dict[str, Any]:
        return await self.request(
            "PATCH",
            f"organizations/{self._identifier(org_id)}/api-keys/{self._identifier(key_id)}",
            payload={"status": "disabled"},
        )
