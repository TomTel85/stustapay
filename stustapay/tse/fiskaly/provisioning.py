"""Idempotent provisioning for Fiskaly SIGN DE TSSs and clients."""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Protocol
from uuid import UUID

from pydantic import SecretStr

from .client import FiskalyAdminAuthenticationError, FiskalyClient, FiskalyError, FiskalyHTTPError


class PukStorage(Protocol):
    """The synchronous secure storage operations required by provisioning."""

    def load(self, tss_id: UUID) -> SecretStr | None: ...

    def save(self, tss_id: UUID, puk: str) -> None: ...


class FiskalyProvisioner:
    """Provision a configured TSS and its tills using caller-assigned UUIDs."""

    def __init__(self, client: FiskalyClient):
        self.client = client
        self.config = client.config

    @property
    def tss_path(self) -> str:
        return f"tss/{self.config.tss_id}"

    def _verify(self, value: dict[str, Any], *, identity: str, path: str) -> dict[str, Any]:
        if value.get("_id") != identity:
            raise FiskalyError(f"Fiskaly {path} response has an unexpected identity")
        if value.get("_env") != self.config.environment:
            raise FiskalyError(f"Fiskaly {path} belongs to a different environment")
        return value

    async def _get_tss(self) -> dict[str, Any] | None:
        try:
            result = await self.client.request("GET", self.tss_path)
        except FiskalyHTTPError as exc:
            if exc.status == 404:
                return None
            raise
        return self._verify(result, identity=str(self.config.tss_id), path="TSS")

    async def _create_or_recover_tss(self) -> dict[str, Any]:
        try:
            result = await self.client.request("PUT", self.tss_path, payload={})
        except FiskalyHTTPError as exc:
            if exc.status != 409:
                raise
            # A previous request may have created this exact UUID while losing
            # its response. Reconcile by identity; never allocate a replacement.
            existing = await self._get_tss()
            if existing is None:
                raise FiskalyError("Fiskaly TSS creation conflicted but the TSS could not be recovered") from None
            return existing
        self._verify(result, identity=str(self.config.tss_id), path="TSS")
        return result

    async def ensure_tss(self, store: PukStorage) -> dict[str, Any]:
        """Ensure the configured TSS is initialized, without resetting an active PIN."""
        assert self.config.tss_id is not None, "Fiskaly TSS ID must be resolved before provisioning"
        tss_id = self.config.tss_id
        tss = await self._get_tss()
        if tss is None:
            tss = await self._create_or_recover_tss()

        state = tss.get("state")
        if state == "INITIALIZED":
            self._verify_initialized(tss)
            return tss
        if state in {"DISABLED", "DEFECTIVE", "DELETED"}:
            raise FiskalyError(f"Fiskaly TSS is in unsupported state {state}")
        if state not in {"CREATED", "UNINITIALIZED"}:
            raise FiskalyError("Fiskaly TSS is in an unsupported state")

        puk = store.load(tss_id)
        created = state == "CREATED"
        if created:
            # GET commonly omits admin_puk. The idempotent PUT for the same UUID
            # is the documented recovery path for its one-time provisioning key.
            if not isinstance(tss.get("admin_puk"), str):
                recovered = await self._create_or_recover_tss()
                if isinstance(recovered.get("admin_puk"), str):
                    tss = recovered
            admin_puk = tss.get("admin_puk")
            if isinstance(admin_puk, str) and admin_puk:
                store.save(tss_id, admin_puk)
                puk = SecretStr(admin_puk)
            if puk is None:
                raise FiskalyError("Fiskaly TSS provisioning key is unavailable")

            # Persist the one-time key before any state transition can consume it.
            uninitialized = await self.client.request(
                "PATCH", self.tss_path, payload={"state": "UNINITIALIZED"}, request_timeout=30
            )
            self._verify(uninitialized, identity=str(tss_id), path="TSS")
            if uninitialized.get("state") != "UNINITIALIZED":
                raise FiskalyError("Fiskaly TSS did not enter the uninitialized state")

        pin = self.config.admin_pin
        if pin is None:
            raise FiskalyError("Fiskaly administrator PIN is not configured")
        if created:
            assert puk is not None
            await self._set_initial_pin(puk, pin)
        try:
            async with self.admin_session():
                initialized = await self.client.request(
                    "PATCH", self.tss_path, payload={"state": "INITIALIZED"}, request_timeout=30
                )
            self._verify_initialized(initialized)
            return self._verify(initialized, identity=str(tss_id), path="TSS")
        except FiskalyAdminAuthenticationError:
            # On restart the initial PIN change may have committed while its
            # response was lost. Retry only through the saved PUK, then verify
            # the configured PIN once more. Never include either secret in errors.
            saved_puk = store.load(tss_id) or puk
            if saved_puk is None:
                raise
            await self._set_initial_pin(saved_puk, pin)
            async with self.admin_session():
                initialized = await self.client.request(
                    "PATCH", self.tss_path, payload={"state": "INITIALIZED"}, request_timeout=30
                )
            self._verify_initialized(initialized)
            return self._verify(initialized, identity=str(tss_id), path="TSS")

    @staticmethod
    def _verify_initialized(tss: dict[str, Any]) -> None:
        if tss.get("state") != "INITIALIZED":
            raise FiskalyError("Fiskaly TSS did not enter the initialized state")

    async def _set_initial_pin(self, puk: SecretStr, pin: SecretStr) -> None:
        try:
            await self.client.request(
                "PATCH",
                f"{self.tss_path}/admin",
                payload={"admin_puk": puk.get_secret_value(), "new_admin_pin": pin.get_secret_value()},
                request_timeout=30,
                refresh_on_unauthorized=False,
            )
        except FiskalyHTTPError as exc:
            if exc.status == 401:
                raise FiskalyAdminAuthenticationError("Fiskaly administrator authentication failed") from None
            raise

    @asynccontextmanager
    async def admin_session(self) -> AsyncIterator[None]:
        """Authenticate with the TSS administrator and always attempt logout."""
        pin = self.config.admin_pin
        if pin is None:
            raise FiskalyError("Fiskaly administrator PIN is not configured")
        try:
            await self._login(pin)
        except BaseException:
            await self._logout(suppress_error=True)
            raise
        try:
            yield
        except BaseException:
            await self._logout(suppress_error=True)
            raise
        else:
            await self._logout(suppress_error=False)

    async def _logout(self, *, suppress_error: bool) -> None:
        try:
            await self.client.request(
                "POST", f"{self.tss_path}/admin/logout", payload={}, refresh_on_unauthorized=False
            )
        except FiskalyError:
            if not suppress_error:
                raise FiskalyError("Fiskaly administrator session could not be closed") from None

    async def _login(self, pin: SecretStr) -> None:
        try:
            await self.client.request(
                "POST",
                f"{self.tss_path}/admin/auth",
                payload={"admin_pin": pin.get_secret_value()},
                refresh_on_unauthorized=False,
            )
        except FiskalyHTTPError as exc:
            if exc.status == 401:
                raise FiskalyAdminAuthenticationError("Fiskaly administrator authentication failed") from None
            raise

    async def ensure_client(self, client_id: UUID, till_serial: str) -> dict[str, Any]:
        """Ensure one till binding exists with its preassigned client UUID."""
        if self.config.tss_id is None:
            raise FiskalyError("Fiskaly TSS ID is not configured")
        if client_id.version != 4:
            raise FiskalyError("Fiskaly client IDs must be UUIDv4")
        path = f"{self.tss_path}/client/{client_id}"
        try:
            result = await self.client.request("GET", path)
        except FiskalyHTTPError as exc:
            if exc.status != 404:
                raise
            try:
                result = await self.client.request("PUT", path, payload={"serial_number": till_serial})
            except FiskalyHTTPError as create_error:
                if create_error.status != 409:
                    raise
                # A lost response or concurrent owner may have completed the
                # same UUID. Read and validate that exact object.
                try:
                    result = await self.client.request("GET", path)
                except FiskalyHTTPError:
                    raise FiskalyError(
                        "Fiskaly client creation conflicted but the client could not be recovered"
                    ) from None

        self._verify(result, identity=str(client_id), path="client")
        if result.get("tss_id") != str(self.config.tss_id):
            raise FiskalyError("Fiskaly client belongs to a different TSS")
        if result.get("serial_number") != till_serial:
            raise FiskalyError("Fiskaly client serial number does not match the till")
        if result.get("state") != "REGISTERED":
            raise FiskalyError("Fiskaly client is not registered")
        return result
