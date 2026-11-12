"""Durable onboarding and provider/customer authorization tests."""

# pylint: disable=redefined-outer-name,unexpected-keyword-arg,missing-kwoa
import asyncio
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sftkit.error import AccessDenied, InvalidArgument

from stustapay.core.schema.fiskaly import NewFiskalyProvisioningJob, NewFiskalySite
from stustapay.core.schema.tree import CopyEventOptions, CopyEventRequest
from stustapay.core.schema.tse import NewTse, TseType
from stustapay.core.service.fiskaly import FiskalyService
from stustapay.core.service.tse import TseService
from stustapay.tests import test_tse_fiskaly as cloud_tests
from stustapay.tse.fiskaly import onboarding
from stustapay.tse.fiskaly.client import FiskalyError, FiskalyTransportError
from stustapay.tse.fiskaly.config import (
    FiskalyManagementCredentials,
    FiskalyManagementSettings,
    FiskalySettings,
)
from stustapay.tse.fiskaly.onboarding import FiskalyOnboardingRunner, resolve_managed_config
from stustapay.tse.fiskaly.secrets import CredentialVault
from stustapay.tse.signature_processor import SignatureProcessor

provider = cloud_tests.provider


class ManagementFixture:
    def __init__(self):
        self.organizations = []
        self.keys = []
        self.creations = 0
        self.key_creations = 0
        self.lose_org = False
        self.lose_key = False
        self.bad_group = False
        self.disabled = []

    def client(self, config):
        fixture = self

        class Client:
            def __init__(self):
                self.config = config

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def list_organizations(self):
                return fixture.organizations

            async def create_organization(self, payload):
                fixture.creations += 1
                org = {**payload, "_id": str(uuid4()), "_type": "MANAGED_ORGANIZATION", "_envs": ["TEST"]}
                if fixture.bad_group:
                    org["managed_by_organization_id"] = str(uuid4())
                fixture.organizations.append(org)
                if fixture.lose_org:
                    fixture.lose_org = False
                    raise FiskalyTransportError("lost organization response")
                return org

            async def get_organization(self, org_id):
                return next(org for org in fixture.organizations if org["_id"] == str(org_id))

            async def enable_environment(self, org_id):
                org = await self.get_organization(org_id)
                org["_envs"].append(config.environment)
                return {"_success": True}

            async def list_keys(self, _):
                return fixture.keys

            async def create_key(self, _, name, metadata):
                fixture.key_creations += 1
                key = {
                    "_id": str(uuid4()),
                    "name": name,
                    "metadata": metadata,
                    "key": "test-key",
                    "secret": "test-secret",
                    "status": "enabled",
                }
                fixture.keys.append({k: v for k, v in key.items() if k != "secret"})
                if fixture.lose_key:
                    fixture.lose_key = False
                    raise FiskalyTransportError("lost key response")
                return key

            async def disable_key(self, _, key_id):
                fixture.disabled.append(key_id)
                next(k for k in fixture.keys if k["_id"] == str(key_id))["status"] = "disabled"
                return {"_success": True}

        return Client()


@pytest.fixture
async def setup(config, setup_test_db_pool, auth_service, event_node, global_admin_token, tmp_path, monkeypatch):
    management = FiskalyManagementSettings(
        enabled=True,
        secret_key=SecretStr(Fernet.generate_key().decode()),
        puk_directory=tmp_path / "puks",
        environments={
            "TEST": FiskalyManagementCredentials(group_id=uuid4(), api_key="group-key", api_secret="group-secret")
        },
    )
    cfg = config.model_copy(update={"fiskaly": FiskalySettings(management=management)})
    service = FiskalyService(setup_test_db_pool, cfg, auth_service)
    fixture = ManagementFixture()
    monkeypatch.setattr(onboarding, "FiskalyManagementClient", fixture.client)
    site = await service.create_site(
        token=global_admin_token,
        node_id=event_node.id,
        site=NewFiskalySite(
            customer_node_id=event_node.id,
            name="Main stage",
            operator_name="Example Operator",
            address_line1="Teststrasse 1",
            zip="12345",
            town="Berlin",
            vat_id="DE123456789",
        ),
    )
    job = await service.start_provisioning(
        token=global_admin_token,
        node_id=event_node.id,
        request=NewFiskalyProvisioningJob(site_id=site.id, event_node_id=event_node.id),
    )
    return service, cfg, fixture, site, job


@pytest.fixture
async def sign_bridge(setup, provider, monkeypatch):
    _, cfg, fixture, _, _ = setup
    original = FiskalyOnboardingRunner.ensure_tse

    async def ensure_tse(self, conn, job):
        await original(self, conn, job)
        cloud = await resolve_managed_config(conn, cfg, job["id"])
        provider.config = cloud
        provider.master["_id"] = str(cloud.tss_id)
        provider.master["max_number_registered_clients"] = 100
        provider.admin_pin = cloud.admin_pin.get_secret_value()
        provider.clients.clear()

    monkeypatch.setattr(FiskalyOnboardingRunner, "ensure_tse", ensure_tse)
    return fixture


@pytest.mark.usefixtures("sign_bridge")
async def test_onboarding_creates_encrypted_credentials_and_registers_till(
    setup,
    till,
    db_connection,
    setup_test_db_pool,
    event_admin_token,
    event_node,
):
    service, cfg, remote, site, job = setup
    await FiskalyOnboardingRunner(cfg).process(db_connection, job.id)
    result = (await service.site_status(token=event_admin_token, node_id=event_node.id, site_id=site.id))[0]
    assert result.status == "ready"
    assert result.tse_id is not None
    assert await db_connection.fetchval("select tse_id from till where id=$1", till.id) == result.tse_id
    assert await db_connection.fetchval("select registered from fiskaly_client_binding where till_id=$1", till.id)
    assert remote.creations == remote.key_creations == 1
    assert remote.organizations[0]["vat_id"] == "DE123456789"
    ciphertext = await db_connection.fetchval(
        "select credential_ciphertext from fiskaly_site_environment where site_id=$1", site.id
    )
    assert "test-secret" not in ciphertext
    assert "test-secret" not in result.model_dump_json()
    cloud = await resolve_managed_config(db_connection, cfg, job.id)
    assert cloud.api_secret.get_secret_value() == "test-secret"
    assert cloud.customer_node_id == event_node.id
    # Dynamic controller discovery must pick up a completed job without restart.
    processor = SignatureProcessor(cfg)
    processor.db_pool = setup_test_db_pool
    import contextlib

    async with contextlib.AsyncExitStack() as stack:
        await processor.refresh_workers(stack)
        assert result.tse_id in processor.tses
    assert "test-secret" not in result.model_dump_json()


@pytest.mark.usefixtures("sign_bridge")
async def test_lost_organization_response_reconciles_same_unit(setup, db_connection):
    _, cfg, remote, site, job = setup
    remote.lose_org = True
    runner = FiskalyOnboardingRunner(cfg)
    await runner.process(db_connection, job.id)
    assert await db_connection.fetchval("select organization_id from fiskaly_site where id=$1", site.id) is None
    await runner.process(db_connection, job.id)
    assert await db_connection.fetchval("select status from fiskaly_provisioning_job where id=$1", job.id) == "ready", (
        await db_connection.fetchval("select last_error from fiskaly_provisioning_job where id=$1", job.id)
    )
    assert remote.creations == 1


@pytest.mark.usefixtures("sign_bridge")
async def test_lost_key_secret_requires_explicit_replacement(setup, db_connection, global_admin_token, event_node):
    service, cfg, remote, _, job = setup
    remote.lose_key = True
    runner = FiskalyOnboardingRunner(cfg)
    await runner.process(db_connection, job.id)
    await runner.process(db_connection, job.id)
    assert (
        await db_connection.fetchval("select step from fiskaly_provisioning_job where id=$1", job.id)
        == "key_secret_missing"
    )
    assert remote.key_creations == 1
    assert not remote.disabled
    await service.retry_provisioning(token=global_admin_token, node_id=event_node.id, job_id=job.id)
    await runner.process(db_connection, job.id)
    assert remote.key_creations == 2
    assert len(remote.disabled) == 1
    assert await db_connection.fetchval("select status from fiskaly_provisioning_job where id=$1", job.id) == "ready", (
        await db_connection.fetchval("select last_error from fiskaly_provisioning_job where id=$1", job.id)
    )


async def test_duplicate_start_returns_same_job_and_customer_admin_cannot_mutate(
    setup,
    event_node,
    event_admin_token,
    global_admin_token,
):
    service, _, _, site, job = setup
    request = NewFiskalyProvisioningJob(site_id=site.id, event_node_id=event_node.id)
    duplicates = await asyncio.gather(
        *[
            service.start_provisioning(token=global_admin_token, node_id=event_node.id, request=request)
            for _ in range(2)
        ]
    )
    assert [entry.id for entry in duplicates] == [job.id, job.id]
    with pytest.raises(AccessDenied):
        await service.start_provisioning(token=event_admin_token, node_id=event_node.id, request=request)
    with pytest.raises(AccessDenied):
        await service.retry_provisioning(token=event_admin_token, node_id=event_node.id, job_id=job.id)


async def test_foreign_event_cannot_use_site_and_status_is_scoped(
    setup,
    event_node,
    event_admin_token,
    global_admin_token,
    tree_service,
):
    service, _, _, site, _ = setup
    foreign = await tree_service.copy_event(
        token=global_admin_token,
        node_id=event_node.id,
        request=CopyEventRequest(name=f"Foreign-{uuid4()}", description="", options=CopyEventOptions()),
    )
    with pytest.raises(InvalidArgument, match="belonging"):
        await service.start_provisioning(
            token=global_admin_token,
            node_id=foreign.id,
            request=NewFiskalyProvisioningJob(site_id=site.id, event_node_id=foreign.id),
        )
    assert await service.site_status(token=global_admin_token, node_id=foreign.id, site_id=site.id) == []
    visible = await service.list_sites(token=global_admin_token, node_id=foreign.id)
    assert site.id not in [s.id for s in visible]
    assert len(await service.site_status(token=event_admin_token, node_id=event_node.id, site_id=site.id)) == 1


async def test_wrong_group_blocks_before_key_creation(setup, db_connection):
    _, cfg, remote, _, job = setup
    remote.bad_group = True
    await FiskalyOnboardingRunner(cfg).process(db_connection, job.id)
    assert remote.key_creations == 0
    assert (
        await db_connection.fetchval("select status from fiskaly_provisioning_job where id=$1", job.id)
        == "action_required"
    )


async def test_unknown_org_result_never_posts_again(setup, db_connection):
    _, cfg, remote, site, job = setup
    remote.lose_org = True
    runner = FiskalyOnboardingRunner(cfg)
    await runner.process(db_connection, job.id)
    remote.organizations.clear()  # Simulate temporary provider invisibility.
    await runner.process(db_connection, job.id)
    assert remote.creations == 1
    assert (
        await db_connection.fetchval("select status from fiskaly_provisioning_job where id=$1", job.id)
        == "action_required"
    )
    assert await db_connection.fetchval("select creation_started from fiskaly_site where id=$1", site.id)


async def test_live_event_cannot_replace_test_identity(setup, event_node, global_admin_token):
    service, cfg, _, site, _ = setup
    cfg.fiskaly.management.environments["LIVE"] = cfg.fiskaly.management.environments["TEST"].model_copy(
        update={"environment": "LIVE"}
    )
    with pytest.raises(InvalidArgument, match="cannot change"):
        await service.start_provisioning(
            token=global_admin_token,
            node_id=event_node.id,
            request=NewFiskalyProvisioningJob(site_id=site.id, event_node_id=event_node.id, environment="LIVE"),
        )


async def test_unbound_yaml_profiles_are_provider_only(
    setup, provider, auth_service, setup_test_db_pool, event_node, event_admin_token
):
    _, cfg, _, _, _ = setup
    cfg.fiskaly.profiles["other-customer"] = provider.config
    service = TseService(setup_test_db_pool, cfg, auth_service)
    with pytest.raises(InvalidArgument, match="provider administration"):
        await service.create_tse(
            token=event_admin_token,
            node_id=event_node.id,
            new_tse=NewTse(name="Wrong", type=TseType.fiskaly, fiskaly_profile="other-customer"),
        )


def test_vault_rejects_changed_record_binding():
    key = SecretStr(Fernet.generate_key().decode())
    vault = CredentialVault(key)
    encrypted = vault.encrypt("customer-a", {"api_secret": "private"})
    with pytest.raises(FiskalyError, match="another resource"):
        vault.decrypt("customer-b", encrypted)
    with pytest.raises(FiskalyError):
        CredentialVault(SecretStr(Fernet.generate_key().decode())).decrypt("customer-a", encrypted)


@pytest.mark.usefixtures("sign_bridge")
async def test_shared_site_reuses_unit_key_but_creates_distinct_event_tses(
    setup,
    db_connection,
    event,
    global_admin_token,
    tree_service,
):
    from stustapay.core.schema.tree import NewEvent, NewNode
    from stustapay.core.service.tree.service import COPY_EVENT_SETTINGS_MODEL_EXCLUDES

    service, cfg, remote, _, _ = setup
    customer = await tree_service.create_node(
        token=global_admin_token,
        node_id=0,
        new_node=NewNode(name=f"Customer-{uuid4()}", description=""),
    )
    events = []
    for _ in range(2):
        payload = event.model_dump(exclude=COPY_EVENT_SETTINGS_MODEL_EXCLUDES)
        payload.update(name=f"Shared-site-{uuid4()}", description="", customer_portal_url="")
        copied = await tree_service.create_event(
            token=global_admin_token,
            node_id=customer.id,
            event=NewEvent.model_validate(payload),
        )
        events.append(copied)
    site = await service.create_site(
        token=global_admin_token,
        node_id=customer.id,
        site=NewFiskalySite(
            customer_node_id=customer.id,
            name="Shared site",
            operator_name="Shared operator",
            address_line1="Teststrasse 1",
            zip="12345",
            town="Berlin",
        ),
    )
    runner = FiskalyOnboardingRunner(cfg)
    ids = []
    for event in events:
        job = await service.start_provisioning(
            token=global_admin_token,
            node_id=event.id,
            request=NewFiskalyProvisioningJob(site_id=site.id, event_node_id=event.id),
        )
        await runner.process(db_connection, job.id)
        result = await db_connection.fetchrow(
            "select status,tse_id,last_error from fiskaly_provisioning_job where id=$1", job.id
        )
        assert result["status"] == "ready", result["last_error"]
        ids.append(result["tse_id"])
    assert len(set(ids)) == 2
    assert remote.creations == remote.key_creations == 1
    assert len(await service.site_status(token=global_admin_token, node_id=customer.id, site_id=site.id)) == 2
    assert len(await service.site_status(token=global_admin_token, node_id=events[0].id, site_id=site.id)) == 1


@pytest.mark.parametrize("count,expected", [(100, "ready"), (101, "action_required")])
@pytest.mark.usefixtures("sign_bridge")
async def test_onboarding_respects_reported_hundred_client_capacity(
    setup,
    db_connection,
    event_node,
    till_profile,
    provider,
    count,
    expected,
):
    _, cfg, _, _, job = setup
    # Events already contain a virtual till, which also needs a fiscal client.
    existing = await db_connection.fetchval("select count(*) from till where node_id=$1", event_node.id)
    for index in range(count - existing):
        await db_connection.execute(
            "insert into till(node_id,name,description,active_profile_id) values($1,$2,'',$3)",
            event_node.id,
            f"Capacity-{event_node.id}-{index}",
            till_profile.id,
        )
    await FiskalyOnboardingRunner(cfg).process(db_connection, job.id)
    assert await db_connection.fetchval("select status from fiskaly_provisioning_job where id=$1", job.id) == expected
    if count == 100:
        assert len(provider.created_clients) == 100
    else:
        assert not provider.created_clients


async def test_controller_limit_blocks_before_resource_creation(setup, db_connection):
    _, cfg, remote, _, job = setup
    # Use a zero threshold only in this test to model a full controller.
    cfg.fiskaly.management.max_active_tses = 0
    await FiskalyOnboardingRunner(cfg).process(db_connection, job.id)
    assert not remote.creations
    assert (
        await db_connection.fetchval("select status from fiskaly_provisioning_job where id=$1", job.id)
        == "action_required"
    )


async def test_live_provisioning_cannot_start_before_checkout_support(setup, db_connection, global_admin_token):
    service, cfg, remote, site, job = setup
    await db_connection.execute("delete from fiskaly_provisioning_job where id=$1", job.id)
    cfg.fiskaly.management.environments["LIVE"] = cfg.fiskaly.management.environments["TEST"].model_copy(
        update={"environment": "LIVE"}
    )
    with pytest.raises(InvalidArgument, match="start and end of the fiscal operation"):
        await service.start_provisioning(
            token=global_admin_token,
            node_id=job.event_node_id,
            request=NewFiskalyProvisioningJob(site_id=site.id, event_node_id=job.event_node_id, environment="LIVE"),
        )
    assert not remote.creations
    assert not await db_connection.fetchval(
        "select exists(select 1 from fiskaly_provisioning_job where event_node_id=$1)", job.event_node_id
    )
