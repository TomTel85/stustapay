"""Offline SIGN DE contract tests against a local HTTP provider fixture."""

# pylint: disable=redefined-outer-name

import asyncio
import base64
from dataclasses import replace
from uuid import uuid4

import pytest
from aiohttp import web
from pydantic import SecretStr, ValidationError

from stustapay.tse.fiskaly.client import FiskalyClient, FiskalyError, FiskalyHTTPError, FiskalyTransportError
from stustapay.tse.fiskaly.config import FiskalyConfig
from stustapay.tse.fiskaly.signing import FiskalySigner, FiskalySigningRequest
from stustapay.tse.handler import TSESignatureRequest


@pytest.fixture(autouse=True)
async def setup_test_db_pool():
    yield None


class FiskalyFixture:
    def __init__(self):
        self.config = FiskalyConfig(
            api_key=SecretStr("test-key"), api_secret=SecretStr("test-secret"), tss_id=uuid4(), max_concurrency=4
        )
        self.binding = uuid4()
        self.token = "token-1"
        self.auth_count = 0
        self.unauthorized = False
        self.auth_error = False
        self.error_status = None
        self.invalid_json = False
        self.timeout_state = None
        self.transactions = {}
        self.requests = []
        self.active_requests = 0
        self.peak_requests = 0
        self.admin_pin = "123456"
        self.admin_authenticated = False
        self.client_create_timeout = False
        self.created_clients = []
        self.master = {
            "_id": str(self.config.tss_id),
            "_env": "TEST",
            "state": "INITIALIZED",
            "serial_number": "tss-serial",
            "signature_algorithm": "ecdsa-plain-SHA256",
            "signature_timestamp_format": "unixTime",
            "public_key": "test-public-key",
            "certificate": "test-certificate",
            "transaction_data_encoding": "UTF-8",
        }
        self.client = {
            "_id": str(self.binding),
            "_env": "TEST",
            "tss_id": str(self.config.tss_id),
            "state": "REGISTERED",
            "serial_number": "42",
        }
        self.clients = {str(self.binding): self.client}

    def signing_request(self, till_id="42"):
        binding = self.binding
        if till_id != "42":
            binding = uuid4()
            self.clients[str(binding)] = {
                **self.client,
                "_id": str(binding),
                "serial_number": till_id,
            }
        return FiskalySigningRequest(
            transaction_id=uuid4(),
            client_id=binding,
            request=TSESignatureRequest(7, till_id, "Kassenbeleg-V1", "Beleg^10.00_0.00_0.00_0.00_0.00^10.00:Bar"),
        )

    async def handle(self, request):
        path = request.match_info["path"]
        payload = await request.json() if request.can_read_body else None
        self.requests.append((request.method, path, dict(request.query), payload))
        if path == "auth":
            self.auth_count += 1
            assert payload == {"api_key": "test-key", "api_secret": "test-secret"}
            if self.auth_error:
                return web.json_response({"access_token": ""})
            self.token = f"token-{self.auth_count}"
            return web.json_response(
                {
                    "access_token": self.token,
                    "access_token_claims": {"env": "TEST", "organization_id": str(self.config.organization_id)},
                }
            )
        if self.unauthorized or request.headers.get("Authorization") != f"Bearer {self.token}":
            return web.json_response({"secret": "provider-secret"}, status=401)
        if self.error_status:
            return web.json_response({"secret": "provider-secret"}, status=self.error_status)
        if self.invalid_json:
            return web.Response(text="not json", content_type="application/json")
        if path == f"tss/{self.config.tss_id}":
            return web.json_response(self.master)
        if path.endswith("/admin/auth"):
            if payload != {"admin_pin": self.admin_pin}:
                return web.json_response({}, status=401)
            self.admin_authenticated = True
            return web.json_response({})
        if path.endswith("/admin/logout"):
            self.admin_authenticated = False
            return web.json_response({})
        if "/client/" in path:
            client_id = path.rsplit("/", 1)[1]
            if request.method == "PUT":
                assert isinstance(payload, dict)
                if not self.admin_authenticated:
                    return web.json_response({}, status=401)
                if client_id not in self.clients:
                    self.created_clients.append(client_id)
                    self.clients[client_id] = {
                        "_id": client_id,
                        "_env": "TEST",
                        "tss_id": str(self.config.tss_id),
                        "state": "REGISTERED",
                        "serial_number": payload["serial_number"],
                    }
                if self.client_create_timeout:
                    self.client_create_timeout = False
                    await asyncio.sleep(0.12)
            if client_id not in self.clients:
                return web.json_response({}, status=404)
            return web.json_response(self.clients[client_id])
        tx_id = path.rsplit("/", 1)[1]
        if request.method == "GET":
            if tx_id not in self.transactions:
                return web.json_response({}, status=404)
            return web.json_response(self.transactions[tx_id])
        assert isinstance(payload, dict)
        self.active_requests += 1
        self.peak_requests = max(self.active_requests, self.peak_requests)
        try:
            await asyncio.sleep(0.002)
            revision = int(request.query["tx_revision"])
            assert revision in {1, 2}
            data = self.transactions.get(tx_id, {}).copy()
            if revision == 1:
                assert "schema" not in payload
                data.update(
                    {
                        "_id": tx_id,
                        "_env": "TEST",
                        "tss_id": str(self.config.tss_id),
                        "tss_serial_number": "tss-serial",
                        "client_id": payload["client_id"],
                        "client_serial_number": self.clients[payload["client_id"]]["serial_number"],
                        "number": len(self.transactions) + 1,
                        "time_start": 1700000000,
                        "metadata": payload["metadata"],
                    }
                )
            else:
                data.update(
                    {
                        "time_end": 1700000001,
                        "schema": payload["schema"],
                        "signature": {
                            "value": base64.b64encode(b"fixture-signature").decode(),
                            "algorithm": "ecdsa-plain-SHA256",
                            "counter": "9",
                            "public_key": "test-public-key",
                        },
                    }
                )
            data.update({"state": payload["state"], "revision": revision, "latest_revision": revision})
            self.transactions[tx_id] = data
            if self.timeout_state == payload["state"]:
                self.timeout_state = None
                # Simulate the remote commit succeeding but its response being lost.
                await asyncio.sleep(0.12)
            return web.json_response(data)
        finally:
            self.active_requests -= 1


@pytest.fixture
async def provider(monkeypatch):
    fixture = FiskalyFixture()
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


async def test_signing_maps_raw_payload_and_signature_and_reuses_finished_transaction(provider):
    request = provider.signing_request()
    async with FiskalyClient(provider.config) as client:
        signer = FiskalySigner(client)
        master = await signer.initialize()
        await signer.verify_client(request.client_id, request.request.till_id)
        signature = await signer.sign(request)
        assert await signer.sign(request) == signature
    assert master.tse_serial == "tss-serial"
    assert signature.tse_transaction == "1"
    assert signature.tse_signaturenr == "9"
    assert signature.tse_start == "2023-11-14T22:13:20.000Z"
    assert signature.tse_end == "2023-11-14T22:13:21.000Z"
    assert base64.b64decode(signature.tse_signature) == b"fixture-signature"
    writes = [entry for entry in provider.requests if entry[0] == "PUT"]
    assert [entry[2]["tx_revision"] for entry in writes] == ["1", "2"]
    assert base64.b64decode(writes[1][3]["schema"]["raw"]["process_data"]).decode() == request.request.process_data
    assert provider.auth_count == 1


@pytest.mark.parametrize("state", ["ACTIVE", "FINISHED"])
async def test_lost_response_recovers_same_identity_after_client_restart(provider, state):
    config = provider.config.model_copy(update={"request_timeout": 0.05})
    request = provider.signing_request()
    provider.timeout_state = state
    async with FiskalyClient(config) as client:
        signer = FiskalySigner(client)
        await signer.initialize()
        with pytest.raises(FiskalyTransportError):
            await signer.sign(request)
    async with FiskalyClient(config) as client:
        signer = FiskalySigner(client)
        await signer.initialize()
        await signer.sign(request)
    assert len(provider.transactions) == 1
    writes = [entry for entry in provider.requests if entry[0] == "PUT"]
    assert len(writes) == 2
    assert provider.transactions[str(request.transaction_id)]["state"] == "FINISHED"


async def test_100_tills_use_bounded_parallelism(provider):
    requests = [provider.signing_request(till_id=str(till)) for till in range(100)]
    async with FiskalyClient(provider.config) as client:
        signer = FiskalySigner(client)
        await signer.initialize()
        await asyncio.gather(
            *(signer.verify_client(request.client_id, request.request.till_id) for request in requests)
        )
        results = await asyncio.gather(*(signer.sign(request) for request in requests))
    assert len(results) == len(provider.transactions) == 100
    assert 1 < provider.peak_requests <= provider.config.max_concurrency
    assert provider.auth_count == 1


async def test_token_expiry_and_concurrent_401_refresh_only_once(provider):
    async with FiskalyClient(provider.config) as client:
        await client.request("GET", f"tss/{provider.config.tss_id}")
        provider.token = "expired"
        await asyncio.gather(*(client.request("GET", f"tss/{provider.config.tss_id}") for _ in range(12)))
        assert provider.auth_count == 2
        client._expires_at = 0  # pylint: disable=protected-access
        await client.request("GET", f"tss/{provider.config.tss_id}")
    assert provider.auth_count == 3


async def test_second_401_is_not_retried_forever(provider):
    provider.unauthorized = True
    async with FiskalyClient(provider.config) as client:
        with pytest.raises(FiskalyHTTPError) as error:
            await client.request("GET", f"tss/{provider.config.tss_id}")
    assert error.value.status == 401
    assert provider.auth_count == 2
    assert "provider-secret" not in str(error.value)


@pytest.mark.parametrize("status", [302, 403, 423, 429, 503])
async def test_upstream_errors_are_sanitized_and_not_automatically_retried(provider, status):
    provider.error_status = status
    async with FiskalyClient(provider.config) as client:
        with pytest.raises(FiskalyHTTPError) as error:
            await client.request("GET", f"tss/{provider.config.tss_id}")
    assert error.value.status == status
    assert error.value.retryable == (status in {423, 429} or status >= 500)
    assert len(provider.requests) == 2
    assert "provider-secret" not in str(error.value)


@pytest.mark.parametrize("field,value", [("_env", "LIVE"), ("state", "DISABLED"), ("_id", str(uuid4()))])
async def test_wrong_or_uninitialized_tss_is_rejected(provider, field, value):
    provider.master[field] = value
    async with FiskalyClient(provider.config) as client:
        with pytest.raises(FiskalyError):
            await FiskalySigner(client).initialize()
    assert not provider.transactions


async def test_client_binding_is_verified_without_remote_mutations(provider):
    provider.client["serial_number"] = "other-till"
    async with FiskalyClient(provider.config) as client:
        with pytest.raises(FiskalyError, match="binding"):
            await FiskalySigner(client).verify_client(provider.binding, "42")
    assert not any(entry[0] == "PUT" for entry in provider.requests)


@pytest.mark.parametrize("field,value", [("client_id", str(uuid4())), ("_env", "LIVE"), ("state", "CANCELLED")])
async def test_recovered_transaction_must_match_identity_and_state(provider, field, value):
    request = provider.signing_request()
    async with FiskalyClient(provider.config) as client:
        signer = FiskalySigner(client)
        await signer.initialize()
        await signer.sign(request)
        provider.transactions[str(request.transaction_id)][field] = value
        with pytest.raises(FiskalyError):
            await signer.sign(request)
    assert len([entry for entry in provider.requests if entry[0] == "PUT"]) == 2


async def test_changed_payload_cannot_reuse_finished_signature(provider):
    request = provider.signing_request()
    async with FiskalyClient(provider.config) as client:
        signer = FiskalySigner(client)
        await signer.initialize()
        await signer.sign(request)
        changed = replace(request, request=replace(request.request, process_data="different"))
        with pytest.raises(FiskalyError, match="payload"):
            await signer.sign(changed)


@pytest.mark.parametrize("field,value", [("value", "invalid"), ("counter", -1), ("public_key", "other-key")])
async def test_malformed_signature_is_rejected(provider, field, value):
    request = provider.signing_request()
    async with FiskalyClient(provider.config) as client:
        signer = FiskalySigner(client)
        await signer.initialize()
        await signer.sign(request)
        provider.transactions[str(request.transaction_id)]["signature"][field] = value
        with pytest.raises(FiskalyError):
            await signer.sign(request)


async def test_invalid_auth_or_json_response_is_rejected(provider):
    async with FiskalyClient(provider.config) as client:
        provider.auth_error = True
        with pytest.raises(FiskalyError, match="access token"):
            await client.request("GET", f"tss/{provider.config.tss_id}")
        provider.auth_error = False
        provider.invalid_json = True
        with pytest.raises(FiskalyError, match="invalid JSON"):
            await client.request("GET", f"tss/{provider.config.tss_id}")


def test_credentials_are_masked_and_empty_credentials_rejected():
    config = FiskalyConfig(api_key=SecretStr("private-key"), api_secret=SecretStr("private-secret"), tss_id=uuid4())
    assert "private-key" not in repr(config)
    assert "private-secret" not in config.model_dump_json()
    with pytest.raises(ValidationError):
        FiskalyConfig(api_key=SecretStr(""), api_secret=SecretStr("secret"), tss_id=uuid4())


async def test_active_recovery_rejects_changed_payload(provider):
    config = provider.config.model_copy(update={"request_timeout": 0.05})
    request = provider.signing_request()
    provider.timeout_state = "ACTIVE"
    async with FiskalyClient(config) as client:
        signer = FiskalySigner(client)
        await signer.initialize()
        with pytest.raises(FiskalyTransportError):
            await signer.sign(request)
        changed = replace(request, request=replace(request.request, process_data="changed"))
        with pytest.raises(FiskalyError, match="fingerprint"):
            await signer.sign(changed)
    assert len([entry for entry in provider.requests if entry[0] == "PUT"]) == 1


async def test_unexpected_active_revision_is_not_overwritten(provider):
    config = provider.config.model_copy(update={"request_timeout": 0.05})
    request = provider.signing_request()
    provider.timeout_state = "ACTIVE"
    async with FiskalyClient(config) as client:
        signer = FiskalySigner(client)
        await signer.initialize()
        with pytest.raises(FiskalyTransportError):
            await signer.sign(request)
        provider.transactions[str(request.transaction_id)]["latest_revision"] = 2
        with pytest.raises(FiskalyError, match="revision"):
            await signer.sign(request)


async def test_duplicate_concurrent_request_is_rejected(provider):
    request = provider.signing_request()
    async with FiskalyClient(provider.config) as client:
        signer = FiskalySigner(client)
        await signer.initialize()
        results = await asyncio.gather(signer.sign(request), signer.sign(request), return_exceptions=True)
    assert sum(isinstance(result, FiskalyError) for result in results) == 1
    assert len(provider.transactions) == 1


async def test_signing_requires_successful_initialization(provider):
    async with FiskalyClient(provider.config) as client:
        signer = FiskalySigner(client)
        with pytest.raises(FiskalyError, match="initialized"):
            await signer.sign(provider.signing_request())
    assert not provider.requests


@pytest.mark.parametrize("field,value", [("time_start", "invalid"), ("time_end", 1600000000)])
async def test_invalid_transaction_times_are_rejected(provider, field, value):
    request = provider.signing_request()
    async with FiskalyClient(provider.config) as client:
        signer = FiskalySigner(client)
        await signer.initialize()
        await signer.sign(request)
        provider.transactions[str(request.transaction_id)][field] = value
        with pytest.raises(FiskalyError):
            await signer.sign(request)
