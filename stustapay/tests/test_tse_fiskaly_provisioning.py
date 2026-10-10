"""Provisioning contracts tested against a local Fiskaly HTTP fixture."""

# pylint: disable=redefined-outer-name

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from aiohttp import web
from pydantic import SecretStr

from stustapay.tse.fiskaly.client import (
    FiskalyAdminAuthenticationError,
    FiskalyClient,
    FiskalyError,
    FiskalyTransportError,
)
from stustapay.tse.fiskaly.config import FiskalyConfig
from stustapay.tse.fiskaly.provisioning import FiskalyProvisioner


@pytest.fixture(autouse=True)
async def setup_test_db_pool():
    """These HTTP contract tests do not need PostgreSQL."""
    yield None


class MemoryPukStore:
    def __init__(self, *, fail_save=False):
        self.values = {}
        self.fail_save = fail_save

    def load(self, tss_id: UUID) -> SecretStr | None:
        value = self.values.get(tss_id)
        return SecretStr(value) if value else None

    def save(self, tss_id: UUID, puk: str) -> None:
        if self.fail_save:
            raise OSError("secure store unavailable")
        self.values[tss_id] = puk


class ProvisioningFixture:
    def __init__(self):
        self.tss_id = uuid4()
        self.client_id = uuid4()
        self.api_token = "api-token"
        self.admin_pin = None
        self.admin_authenticated = False
        self.tss = None
        self.clients = {}
        self.requests = []
        self.lose_tss_create_response = False
        self.lose_client_create_response = False
        self.wrong_pin = False
        self.invalid_puk = False
        self.delay_admin_auth_once = False
        self.logout_error = False

    def config(self, *, timeout=1, pin="123456"):
        return FiskalyConfig(
            api_key=SecretStr("fixture-key"),
            api_secret=SecretStr("fixture-secret"),
            tss_id=self.tss_id,
            auto_provision_tss=True,
            auto_provision_clients=True,
            admin_pin=SecretStr(pin),
            puk_directory=Path("/secure/puk"),
            request_timeout=timeout,
        )

    async def handle(self, request):
        path = request.match_info["path"]
        payload = await request.json() if request.can_read_body else None
        self.requests.append((request.method, path, payload))
        if path == "auth":
            return web.json_response({"access_token": self.api_token, "access_token_claims": {"env": "TEST"}})
        if request.headers.get("Authorization") != f"Bearer {self.api_token}":
            return web.json_response({}, status=401)
        if path == f"tss/{self.tss_id}":
            if request.method == "GET":
                if self.tss is None:
                    return web.json_response({}, status=404)
                return web.json_response({key: value for key, value in self.tss.items() if key != "admin_puk"})
            if request.method == "PUT":
                if self.tss is None:
                    self.tss = {
                        "_id": str(self.tss_id),
                        "_env": "TEST",
                        "state": "CREATED",
                        "serial_number": "fixture-tss",
                        "admin_puk": "fixture-one-time-puk",
                    }
                if self.lose_tss_create_response:
                    self.lose_tss_create_response = False
                    await asyncio.sleep(0.1)
                return web.json_response(self.tss)
            if request.method == "PATCH":
                assert self.tss is not None
                assert payload is not None
                self.tss["state"] = payload["state"]
                return web.json_response(self.tss)
        if path == f"tss/{self.tss_id}/admin":
            assert payload is not None
            if self.invalid_puk or payload != {"admin_puk": "fixture-one-time-puk", "new_admin_pin": "123456"}:
                return web.json_response({}, status=401)
            self.admin_pin = payload["new_admin_pin"]
            return web.json_response({"state": "UNINITIALIZED"})
        if path == f"tss/{self.tss_id}/admin/auth":
            if self.delay_admin_auth_once:
                self.delay_admin_auth_once = False
                self.admin_authenticated = True
                await asyncio.sleep(0.1)
                return web.json_response({"state": "AUTHENTICATED"})
            assert payload is not None
            if self.wrong_pin or payload["admin_pin"] != self.admin_pin:
                return web.json_response({}, status=401)
            self.admin_authenticated = True
            return web.json_response({"state": "AUTHENTICATED"})
        if path == f"tss/{self.tss_id}/admin/logout":
            self.admin_authenticated = False
            return web.json_response({}, status=503 if self.logout_error else 200)
        prefix = f"tss/{self.tss_id}/client/"
        if path.startswith(prefix):
            client_id = path.rsplit("/", 1)[1]
            if request.method == "GET":
                if client_id not in self.clients:
                    return web.json_response({}, status=404)
                return web.json_response(self.clients[client_id])
            if request.method == "PUT":
                if client_id not in self.clients:
                    assert payload is not None
                    self.clients[client_id] = {
                        "_id": client_id,
                        "_env": "TEST",
                        "tss_id": str(self.tss_id),
                        "serial_number": payload["serial_number"],
                        "state": "REGISTERED",
                    }
                if self.lose_client_create_response:
                    self.lose_client_create_response = False
                    await asyncio.sleep(0.1)
                return web.json_response(self.clients[client_id])
        return web.json_response({}, status=404)


@pytest.fixture
async def provider(monkeypatch):
    fixture = ProvisioningFixture()
    app = web.Application()
    app.router.add_route("*", "/api/v2/{path:.*}", fixture.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    monkeypatch.setattr("stustapay.tse.fiskaly.client.BASE_URL", f"http://127.0.0.1:{port}/api/v2")
    try:
        yield fixture
    finally:
        await runner.cleanup()


async def test_tss_and_client_provisioning_are_idempotent(provider):
    store = MemoryPukStore()
    async with FiskalyClient(provider.config()) as client:
        provisioner = FiskalyProvisioner(client)
        tss = await provisioner.ensure_tss(store)
        assert tss["state"] == "INITIALIZED"
        await provisioner.ensure_tss(store)
        async with provisioner.admin_session():
            first = await provisioner.ensure_client(provider.client_id, "till-17")
        async with provisioner.admin_session():
            second = await provisioner.ensure_client(provider.client_id, "till-17")
    assert first == second
    assert provider.tss["state"] == "INITIALIZED"
    saved_puk = store.load(provider.tss_id)
    assert saved_puk is not None
    assert saved_puk.get_secret_value() == "fixture-one-time-puk"
    assert len(provider.clients) == 1
    assert sum(method == "PUT" and "/client/" in path for method, path, _ in provider.requests) == 1
    # One failed login during fresh setup still gets a logout attempt.
    assert sum(path.endswith("/admin/logout") for _, path, _ in provider.requests) == 3


async def test_lost_tss_create_response_recovers_same_uuid_and_puk(provider):
    provider.lose_tss_create_response = True
    store = MemoryPukStore()
    config = provider.config(timeout=0.02)
    async with FiskalyClient(config) as client:
        with pytest.raises(FiskalyTransportError):
            await FiskalyProvisioner(client).ensure_tss(store)
    async with FiskalyClient(config) as client:
        tss = await FiskalyProvisioner(client).ensure_tss(store)
    assert tss["_id"] == str(provider.tss_id)
    assert provider.tss["state"] == "INITIALIZED"
    saved_puk = store.load(provider.tss_id)
    assert saved_puk is not None
    assert saved_puk.get_secret_value() == "fixture-one-time-puk"


async def test_lost_client_create_response_recovers_same_uuid(provider):
    provider.tss = {"_id": str(provider.tss_id), "_env": "TEST", "state": "INITIALIZED", "serial_number": "fixture-tss"}
    provider.lose_client_create_response = True
    config = provider.config(timeout=0.02)
    async with FiskalyClient(config) as client:
        provisioner = FiskalyProvisioner(client)
        with pytest.raises(FiskalyTransportError):
            await provisioner.ensure_client(provider.client_id, "till-17")
    async with FiskalyClient(config) as client:
        recovered = await FiskalyProvisioner(client).ensure_client(provider.client_id, "till-17")
    assert recovered["_id"] == str(provider.client_id)
    assert len(provider.clients) == 1


async def test_wrong_environment_refuses_all_tss_mutation(provider):
    provider.tss = {"_id": str(provider.tss_id), "_env": "LIVE", "state": "CREATED"}
    async with FiskalyClient(provider.config()) as client:
        with pytest.raises(FiskalyError, match="different environment"):
            await FiskalyProvisioner(client).ensure_tss(MemoryPukStore())
    assert not any(method in {"PUT", "PATCH"} for method, _, _ in provider.requests)


@pytest.mark.parametrize("state", ["DISABLED", "DEFECTIVE", "DELETED"])
async def test_unsupported_tss_states_are_never_mutated(provider, state):
    provider.tss = {"_id": str(provider.tss_id), "_env": "TEST", "state": state}
    async with FiskalyClient(provider.config()) as client:
        with pytest.raises(FiskalyError, match="unsupported state"):
            await FiskalyProvisioner(client).ensure_tss(MemoryPukStore())
    assert not any(method in {"PUT", "PATCH"} for method, _, _ in provider.requests)


async def test_puk_store_failure_prevents_tss_state_transition(provider):
    async with FiskalyClient(provider.config()) as client:
        with pytest.raises(OSError, match="secure store unavailable"):
            await FiskalyProvisioner(client).ensure_tss(MemoryPukStore(fail_save=True))
    assert provider.tss["state"] == "CREATED"
    assert not any(method == "PATCH" and path == f"tss/{provider.tss_id}" for method, path, _ in provider.requests)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("_env", "LIVE"),
        ("tss_id", str(uuid4())),
        ("serial_number", "another-till"),
        ("state", "DEREGISTERED"),
    ],
)
async def test_existing_mismatched_client_is_refused_without_overwrite(provider, field, value):
    client = {
        "_id": str(provider.client_id),
        "_env": "TEST",
        "tss_id": str(provider.tss_id),
        "serial_number": "till-17",
        "state": "REGISTERED",
    }
    client[field] = value
    provider.clients[str(provider.client_id)] = client
    async with FiskalyClient(provider.config()) as http_client:
        with pytest.raises(FiskalyError):
            await FiskalyProvisioner(http_client).ensure_client(provider.client_id, "till-17")
    assert not any(method == "PUT" for method, _, _ in provider.requests)


async def test_uninitialized_tss_authenticates_existing_pin_without_reset(provider):
    provider.tss = {"_id": str(provider.tss_id), "_env": "TEST", "state": "UNINITIALIZED"}
    provider.admin_pin = "123456"
    store = MemoryPukStore()
    store.save(provider.tss_id, "fixture-one-time-puk")
    async with FiskalyClient(provider.config()) as client:
        initialized = await FiskalyProvisioner(client).ensure_tss(store)
    assert initialized["state"] == "INITIALIZED"
    assert not any(path.endswith("/admin") for _, path, _ in provider.requests)


async def test_ambiguous_admin_auth_does_not_reset_pin_and_can_resume(provider):
    provider.tss = {"_id": str(provider.tss_id), "_env": "TEST", "state": "UNINITIALIZED"}
    provider.admin_pin = "123456"
    provider.delay_admin_auth_once = True
    store = MemoryPukStore()
    store.save(provider.tss_id, "fixture-one-time-puk")
    config = provider.config(timeout=0.02)
    async with FiskalyClient(config) as client:
        with pytest.raises(FiskalyTransportError):
            await FiskalyProvisioner(client).ensure_tss(store)
    assert not any(path.endswith("/admin") for _, path, _ in provider.requests)

    async with FiskalyClient(config) as client:
        initialized = await FiskalyProvisioner(client).ensure_tss(store)
    assert initialized["state"] == "INITIALIZED"
    assert not any(path.endswith("/admin") for _, path, _ in provider.requests)


async def test_invalid_puk_is_reported_as_admin_authentication_error(provider):
    provider.tss = {"_id": str(provider.tss_id), "_env": "TEST", "state": "UNINITIALIZED"}
    provider.admin_pin = "different-pin"
    provider.invalid_puk = True
    store = MemoryPukStore()
    store.save(provider.tss_id, "fixture-one-time-puk")
    async with FiskalyClient(provider.config()) as client:
        with pytest.raises(FiskalyAdminAuthenticationError):
            await FiskalyProvisioner(client).ensure_tss(store)
    assert sum(path.endswith("/admin") for _, path, _ in provider.requests) == 1
    assert sum(path.endswith("/admin/auth") for _, path, _ in provider.requests) == 1


async def test_logout_failure_after_success_is_sanitized(provider):
    provider.tss = {"_id": str(provider.tss_id), "_env": "TEST", "state": "INITIALIZED"}
    provider.admin_pin = "123456"
    provider.logout_error = True
    async with FiskalyClient(provider.config()) as client:
        with pytest.raises(FiskalyError, match="session could not be closed") as error:
            async with FiskalyProvisioner(client).admin_session():
                pass
    assert str(error.value) == "Fiskaly administrator session could not be closed"


async def test_logout_failure_does_not_mask_authentication_error(provider):
    provider.tss = {"_id": str(provider.tss_id), "_env": "TEST", "state": "INITIALIZED"}
    provider.admin_pin = "different-pin"
    provider.wrong_pin = True
    provider.logout_error = True
    async with FiskalyClient(provider.config()) as client:
        with pytest.raises(FiskalyAdminAuthenticationError):
            async with FiskalyProvisioner(client).admin_session():
                pass


async def test_wrong_admin_pin_attempt_does_not_refresh_or_repeat_auth(provider):
    provider.tss = {"_id": str(provider.tss_id), "_env": "TEST", "state": "INITIALIZED"}
    provider.admin_pin = "different-pin"
    provider.wrong_pin = True
    async with FiskalyClient(provider.config()) as client:
        with pytest.raises(FiskalyAdminAuthenticationError):
            async with FiskalyProvisioner(client).admin_session():
                pass
    assert sum(path.endswith("/admin/auth") for _, path, _ in provider.requests) == 1
    assert sum(path.endswith("/admin/logout") for _, path, _ in provider.requests) == 1
    assert sum(path == "auth" for _, path, _ in provider.requests) == 1


async def test_admin_logout_is_attempted_after_success_even_if_logout_fails(provider):
    provider.tss = {"_id": str(provider.tss_id), "_env": "TEST", "state": "INITIALIZED"}
    provider.admin_pin = "123456"
    provider.logout_error = True
    async with FiskalyClient(provider.config()) as client:
        provisioner = FiskalyProvisioner(client)
        with pytest.raises(FiskalyError, match="session could not be closed"):
            async with provisioner.admin_session():
                pass
    assert sum(path.endswith("/admin/logout") for _, path, _ in provider.requests) == 1
