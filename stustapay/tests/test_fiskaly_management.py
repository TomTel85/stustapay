"""Offline contract tests for the fiskaly Management API client."""

# Pytest injects named fixtures; transport boundary tests exercise the private request helpers.
# pylint: disable=redefined-outer-name,protected-access

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr

from stustapay.tse.fiskaly import management
from stustapay.tse.fiskaly.client import FiskalyError, FiskalyHTTPError
from stustapay.tse.fiskaly.management import FiskalyManagementClient


@pytest.fixture(autouse=True)
async def setup_test_db_pool():
    yield None


class MockResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def json(self):
        return self.payload


class MockSession:
    def __init__(self, fixture):
        self.fixture = fixture

    def request(self, method, url, *, json=None, headers=None, allow_redirects=True, **_kwargs):
        from urllib.parse import parse_qs, urlsplit

        parsed = urlsplit(url)
        query = {key: value[0] for key, value in parse_qs(parsed.query).items()}
        path = parsed.path
        fixture = self.fixture
        fixture.calls.append((method, path, query, json, headers or {}, allow_redirects))
        if path == "/api/v0/auth":
            fixture.auth_count += 1
            return MockResponse(
                200,
                {
                    "access_token": f"jwt-{fixture.auth_count}",
                    "access_token_claims": {"env": "TEST", "organization_id": str(fixture.group_id)},
                    "access_token_expires_in": 300,
                },
            )
        if fixture.unauthorized_once:
            fixture.unauthorized_once = False
            return MockResponse(401, {"detail": "sensitive upstream body"})
        if fixture.status != 200:
            return MockResponse(fixture.status, {"detail": "sensitive upstream body"})
        if path == "/api/v0/organizations":
            if method == "POST":
                return MockResponse(200, {"_id": "created-org", **(json or {})})
            if fixture.malformed:
                return MockResponse(200, {"data": "bad", "count": 1})
            offset, limit = int(query.get("offset", 0)), int(query.get("limit", 5000))
            return MockResponse(
                200,
                {"data": fixture.orgs[offset : offset + limit], "count": len(fixture.orgs), "_type": "ORGANIZATION_LIST"},
            )
        if path.endswith("/enable-env"):
            return MockResponse(200, {"_success": True})
        if path.endswith("/api-keys"):
            if method == "POST":
                return MockResponse(
                    200, {"_id": "new-key", "key": "api-key", "secret": "one-time-secret", **(json or {})}
                )
            offset, limit = int(query.get("offset", 0)), int(query.get("limit", 100))
            return MockResponse(
                200, {"data": fixture.keys[offset : offset + limit], "count": len(fixture.keys), "_type": "API_KEY_LIST"}
            )
        if method == "PATCH":
            return MockResponse(200, {"_id": "key-id", **(json or {})})
        if path.endswith("/organizations/one"):
            return MockResponse(200, {"_id": "one", "_type": "ORGANIZATION"})
        return MockResponse(404, {})

    async def close(self):
        return None


@pytest.fixture
async def provider(monkeypatch):
    group_id = uuid4()
    fixture = SimpleNamespace(
        group_id=group_id,
        config=SimpleNamespace(
            api_key=SecretStr("group-key"),
            api_secret=SecretStr("group-secret"),
            group_id=group_id,
            environment="TEST",
            request_timeout=5,
            max_concurrency=2,
        ),
        calls=[],
        auth_count=0,
        orgs=[{"_id": str(uuid4()), "_type": "MANAGED_ORGANIZATION"}],
        keys=[],
        malformed=False,
        status=200,
        unauthorized_once=False,
    )

    monkeypatch.setattr(management.aiohttp, "ClientSession", lambda **_kwargs: MockSession(fixture))
    yield fixture


@pytest.mark.asyncio
async def test_management_operations_and_pagination(provider):
    provider.orgs = [{"_id": f"org-{index}"} for index in range(5002)]
    provider.keys = [{"_id": f"key-{index}"} for index in range(102)]

    async with FiskalyManagementClient(provider.config) as client:
        organizations = await client.list_organizations()
        keys = await client.list_keys("org-1")
        org = await client.get_organization("one")
        created = await client.create_organization({"name": "customer", "managed_by_organization_id": str(provider.group_id)})
        enabled = await client.enable_environment("org-1")
        new_key = await client.create_key("org-1", "customer-key", {"customer_id": "42"})
        disabled = await client.disable_key("org-1", "key-id")

    assert len(organizations) == 5002
    assert len(keys) == 102
    assert org["_id"] == "one"
    assert created["_id"] == "created-org"
    assert enabled == {"_success": True}
    assert new_key["secret"] == "one-time-secret"
    assert disabled["status"] == "disabled"
    assert provider.auth_count == 1
    assert [call[2]["offset"] for call in provider.calls if call[0] == "GET" and call[1] == "/api/v0/organizations"] == [
        "0",
        "5000",
    ]
    org_query = next(call[2] for call in provider.calls if call[0] == "GET" and call[1] == "/api/v0/organizations")
    assert org_query["managed_by_organization_id"] == str(provider.group_id)
    assert [call[2]["offset"] for call in provider.calls if call[0] == "GET" and call[1].endswith("/api-keys")] == [
        "0",
        "100",
    ]
    assert next(call for call in provider.calls if call[1].endswith("/enable-env"))[3] == {"env": "TEST"}
    create_key_call = next(call for call in provider.calls if call[1].endswith("/api-keys") and call[0] == "POST")
    assert create_key_call[3] == {
        "name": "customer-key",
        "status": "enabled",
        "metadata": {"customer_id": "42"},
    }
    assert all(call[4].get("Authorization") for call in provider.calls if call[1] != "/api/v0/auth")
    assert all(call[5] is False for call in provider.calls)


@pytest.mark.asyncio
async def test_auth_claim_mismatch_rejected(provider):
    # Substitute the auth sender to isolate claim validation without network-side token use.
    client = FiskalyManagementClient(provider.config)
    client._session = object()

    async def send(*_args, **_kwargs):
        return {
            "access_token": "wrong",
            "access_token_claims": {"env": "LIVE", "organization_id": "wrong"},
        }

    client._send = send
    with pytest.raises(FiskalyError, match="organization or environment"):
        await client._authenticate()
    client._session = None


@pytest.mark.asyncio
async def test_errors_are_sanitized_and_post_is_not_replayed(provider):
    provider.status = 401
    async with FiskalyManagementClient(provider.config) as client:
        with pytest.raises(FiskalyHTTPError) as error:
            await client.create_organization({"name": "customer"})
    assert error.value.status == 401
    assert "sensitive upstream body" not in str(error.value)
    assert provider.auth_count == 1


@pytest.mark.asyncio
async def test_get_refreshes_auth_once_after_unauthorized(provider):
    provider.unauthorized_once = True
    async with FiskalyManagementClient(provider.config) as client:
        org = await client.get_organization("one")
    assert org["_id"] == "one"
    assert provider.auth_count == 2


@pytest.mark.asyncio
async def test_invalid_list_shape_is_rejected(provider):
    provider.malformed = True
    async with FiskalyManagementClient(provider.config) as client:
        with pytest.raises(FiskalyError, match="list response"):
            await client.list_organizations()


@pytest.mark.asyncio
async def test_client_must_be_open(provider):
    client = FiskalyManagementClient(provider.config)
    with pytest.raises(FiskalyError, match="not open"):
        await client.request("GET", "organizations")
