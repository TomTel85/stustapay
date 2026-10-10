import asyncio
import time
from typing import Any

import aiohttp

from .config import FiskalyConfig

BASE_URL = "https://kassensichv-middleware.fiskaly.com/api/v2"


class FiskalyError(RuntimeError):
    """A sanitized provider error. Never includes response bodies or credentials."""


class FiskalyHTTPError(FiskalyError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"Fiskaly returned HTTP {status}")

    @property
    def retryable(self) -> bool:
        return self.status in {423, 429} or self.status >= 500


class FiskalyTransportError(FiskalyError):
    """The remote result may be unknown; reconcile before repeating a write."""


class FiskalyAdminAuthenticationError(FiskalyError):
    """Stop provisioning until the PIN is corrected and the worker restarted."""


class FiskalyClient:
    """Bounded HTTP transport with cached authentication and one 401 refresh.

    Does not automatically retry fiscal writes on communication errors. The
    signing layer must retrieve the original transaction before recovery.
    """

    def __init__(self, config: FiskalyConfig):
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._token: str | None = None
        self._expires_at = 0.0
        self._auth_lock = asyncio.Lock()
        self._requests = asyncio.Semaphore(config.max_concurrency)

    async def __aenter__(self):
        if self._session is not None:
            raise FiskalyError("Fiskaly client is already open")
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
        request_timeout: float | None = None,
    ) -> dict[str, Any]:
        if self._session is None:
            raise FiskalyError("Fiskaly client is not open")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            async with self._requests:
                async with self._session.request(
                    method,
                    f"{BASE_URL}/{path}",
                    json=payload,
                    headers=headers,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=request_timeout or self.config.request_timeout),
                ) as response:
                    if not 200 <= response.status < 300:
                        raise FiskalyHTTPError(response.status)
                    data = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise FiskalyTransportError("Fiskaly request failed; remote result may be unknown") from None
        except ValueError:
            raise FiskalyError("Fiskaly returned invalid JSON") from None
        if not isinstance(data, dict):
            raise FiskalyError("Fiskaly returned an invalid response object")
        return data

    async def _authenticate(self, rejected_token: str | None = None) -> str:
        async with self._auth_lock:
            # Concurrent callers rejecting the same token reuse a single refresh.
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
                raise FiskalyError("Fiskaly authentication response has no access token")
            claims = data.get("access_token_claims")
            if self.config.auto_provision_tss or self.config.auto_provision_clients or self.config.organization_id:
                if not isinstance(claims, dict) or claims.get("env") not in {
                    self.config.environment,
                    "TESTING" if self.config.environment == "TEST" else "LIVE",
                }:
                    raise FiskalyError("Fiskaly credential environment does not match provisioning configuration")
            if self.config.organization_id and (
                not isinstance(claims, dict) or claims.get("organization_id") != str(self.config.organization_id)
            ):
                raise FiskalyError("Fiskaly credential organization does not match configuration")
            self._token = token
            # SIGN DE access tokens last 24 hours. Refresh conservatively before expiry;
            # a premature expiry is also handled by the bounded 401 refresh below.
            self._expires_at = time.monotonic() + 23 * 60 * 60
            return token

    async def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        refresh_on_unauthorized: bool = True,
        request_timeout: float | None = None,
    ) -> dict[str, Any]:
        token = await self._authenticate()
        try:
            return await self._send(method, path, token=token, payload=payload, request_timeout=request_timeout)
        except FiskalyHTTPError as exc:
            if exc.status != 401 or not refresh_on_unauthorized:
                raise
        token = await self._authenticate(rejected_token=token)
        return await self._send(method, path, token=token, payload=payload, request_timeout=request_timeout)
