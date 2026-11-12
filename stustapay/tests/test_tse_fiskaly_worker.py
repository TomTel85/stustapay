# pylint: disable=redefined-outer-name
# Service decorators inject connection/node and expose token/node_id to callers.
# pylint: disable=unexpected-keyword-arg,missing-kwoa
import asyncio
import time
from uuid import uuid4

import asyncpg
import pytest
from pydantic import SecretStr
from sftkit.error import InvalidArgument

from stustapay.core.schema.order import OrderType, PaymentMethod
from stustapay.core.schema.tse import NewTse, TseType, UpdateTse
from stustapay.core.service.order.booking import book_order
from stustapay.core.service.tree.common import fetch_restricted_event_settings_for_node
from stustapay.core.service.tse import TseService
from stustapay.dsfinvk.generator import Generator
from stustapay.tests import test_tse_fiskaly as fiskaly_tests
from stustapay.tse.fiskaly.client import FiskalyClient, FiskalyError, FiskalyHTTPError, FiskalyTransportError
from stustapay.tse.fiskaly.config import FiskalySettings
from stustapay.tse.fiskaly.signing import FiskalySigner
from stustapay.tse.fiskaly.worker import MAX_SIGNING_ATTEMPTS, FiskalyWorker

provider = fiskaly_tests.provider


@pytest.fixture
async def cloud_worker(provider, config, setup_test_db_pool, auth_service, event_admin_token, event_node, till):
    provider.client["serial_number"] = str(till.id)
    provider.config = provider.config.model_copy(
        update={
            "clients": {str(till.id): provider.binding},
            "customer_node_id": event_node.id,
            "organization_id": uuid4(),
        }
    )
    profile_name = f"pilot-{uuid4()}"
    service_config = config.model_copy(update={"fiskaly": FiskalySettings(profiles={profile_name: provider.config})})
    service = TseService(setup_test_db_pool, service_config, auth_service)
    tse = await service.create_tse(
        token=event_admin_token,
        node_id=event_node.id,
        new_tse=NewTse(name=f"Cloud-{uuid4()}", type=TseType.fiskaly, fiskaly_profile=profile_name),
    )
    return FiskalyWorker(tse, provider.config), service


async def booked(conn, cashier, till):
    return await book_order(
        conn=conn,
        order_type=OrderType.sale,
        payment_method=PaymentMethod.tag,
        cashier_id=cashier.id,
        till_id=till.id,
        line_items=[],
        bookings={},
    )


@pytest.mark.parametrize("state", ["ACTIVE", "FINISHED"])
async def test_db_worker_restart_recovers_same_persisted_transaction(
    cloud_worker, provider, db_connection, setup_test_db_pool, cashier, till, state
):
    worker, _ = cloud_worker
    config = provider.config.model_copy(update={"request_timeout": 0.05})
    worker.config = config
    order = await booked(db_connection, cashier, till)
    provider.timeout_state = state
    async with FiskalyClient(config) as client:
        signer = FiskalySigner(client)
        await worker.configure(db_connection, signer)
        await worker.process(setup_test_db_pool, signer, order.id)
    original = await db_connection.fetchrow("select * from tse_signature where id=$1", order.id)
    assert original["signature_status"] == "pending"
    assert original["fiskaly_transaction_id"] is not None
    assert original["fiskaly_last_error"] is not None
    assert len(provider.transactions) == 1
    restarted = FiskalyWorker(worker.tse, config)
    async with FiskalyClient(config) as client:
        signer = FiskalySigner(client)
        await restarted.configure(db_connection, signer)
        await restarted.process(setup_test_db_pool, signer, order.id)
    recovered = await db_connection.fetchrow("select * from tse_signature where id=$1", order.id)
    assert recovered["signature_status"] == "done"
    assert recovered["fiskaly_transaction_id"] == original["fiskaly_transaction_id"]
    assert recovered["fiskaly_request"] == original["fiskaly_request"]
    assert recovered["fiskaly_client_id"] == original["fiskaly_client_id"]
    assert recovered["fiskaly_last_error"] is None
    assert len(provider.transactions) == 1
    assert await db_connection.fetchval("select count(*) from bon where id=$1", order.id) == 1


async def test_prepared_payload_cannot_change_in_database(cloud_worker, provider, db_connection, cashier, till):
    worker, _ = cloud_worker
    order = await booked(db_connection, cashier, till)
    async with FiskalyClient(provider.config) as client:
        await worker.configure(db_connection, FiskalySigner(client))
    first = await worker.prepare(db_connection, order.id)
    second = await worker.prepare(db_connection, order.id)
    assert first == second
    with pytest.raises(asyncpg.RaiseError, match="immutable"):
        await db_connection.execute("update tse_signature set fiskaly_transaction_id=$2 where id=$1", order.id, uuid4())


async def test_worker_rejects_foreign_event_binding(cloud_worker, provider, db_connection):
    worker, _ = cloud_worker
    worker.tse = worker.tse.model_copy(update={"node_id": -1})
    async with FiskalyClient(provider.config) as client:
        with pytest.raises(FiskalyError, match="customer organization"):
            await worker.configure(db_connection, FiskalySigner(client))
    assert not provider.transactions


async def test_active_profile_cannot_change(cloud_worker, provider, db_connection, event_admin_token, event_node):
    worker, service = cloud_worker
    service.config.fiskaly.profiles["replacement"] = provider.config
    async with FiskalyClient(provider.config) as client:
        await worker.configure(db_connection, FiskalySigner(client))
    with pytest.raises(InvalidArgument, match="cannot change"):
        await service.update_tse(
            token=event_admin_token,
            node_id=event_node.id,
            tse_id=worker.tse.id,
            updated_tse=UpdateTse(name="Cloud", fiskaly_profile="replacement"),
        )


async def test_advisory_lock_prevents_second_worker_owner(cloud_worker, setup_test_db_pool, db_connection):
    worker, _ = cloud_worker
    lock = f"stustapay:fiskaly:{worker.tse.id}"
    assert await db_connection.fetchval("select pg_try_advisory_lock(hashtextextended($1,0))", lock)
    try:
        async with setup_test_db_pool.acquire() as other:
            assert not await other.fetchval("select pg_try_advisory_lock(hashtextextended($1,0))", lock)
    finally:
        await db_connection.execute("select pg_advisory_unlock(hashtextextended($1,0))", lock)


async def test_profile_creation_requires_server_profile(
    config, auth_service, setup_test_db_pool, event_node, event_admin_token
):
    service = TseService(setup_test_db_pool, config, auth_service)
    with pytest.raises(InvalidArgument, match="server credential profile"):
        await service.create_tse(
            token=event_admin_token,
            node_id=event_node.id,
            new_tse=NewTse(name="Cloud", type=TseType.fiskaly, fiskaly_profile="absent"),
        )


async def test_remote_success_before_local_commit_recovers_without_another_write(
    cloud_worker, provider, db_connection, setup_test_db_pool, cashier, till
):
    worker, _ = cloud_worker
    order = await booked(db_connection, cashier, till)
    async with FiskalyClient(provider.config) as client:
        signer = FiskalySigner(client)
        await worker.configure(db_connection, signer)
        prepared = await worker.prepare(db_connection, order.id)
        await signer.sign(prepared)
    # Simulate death after the remote success, before the local completion update.
    assert await db_connection.fetchval("select signature_status from tse_signature where id=$1", order.id) == "pending"
    async with FiskalyClient(provider.config) as client:
        signer = FiskalySigner(client)
        await worker.configure(db_connection, signer)
        await worker.process(setup_test_db_pool, signer, order.id)
    assert len([request for request in provider.requests if request[0] == "PUT"]) == 2
    assert await db_connection.fetchval("select signature_status from tse_signature where id=$1", order.id) == "done"


async def test_actual_worker_run_processes_queue_and_releases_ownership(
    cloud_worker, db_connection, setup_test_db_pool, cashier, till
):
    worker, _ = cloud_worker
    order = await booked(db_connection, cashier, till)
    worker.start(setup_test_db_pool)
    try:

        async def wait_for_done():
            while (
                await db_connection.fetchval("select signature_status from tse_signature where id=$1", order.id)
                != "done"
            ):
                await asyncio.sleep(0.02)

        await asyncio.wait_for(wait_for_done(), timeout=3)
    finally:
        await worker.stop()
    lock = f"stustapay:fiskaly:{worker.tse.id}"
    assert await db_connection.fetchval("select pg_try_advisory_lock(hashtextextended($1,0))", lock)
    await db_connection.execute("select pg_advisory_unlock(hashtextextended($1,0))", lock)


async def test_export_refuses_open_signatures_instead_of_omitting_booked_order(
    config, db_connection, event_node, cashier, till
):
    order = await booked(db_connection, cashier, till)
    settings = await fetch_restricted_event_settings_for_node(conn=db_connection, node_id=event_node.id)
    generator = Generator(config, event_node.id, "unused.zip", "unused.xml", "unused.dtd", False)
    with pytest.raises(RuntimeError, match="open signatures"):
        await generator.einzelaufzeichnungsmodul(db_connection, till.z_nr, order.booked_at, till.id, settings)


async def test_automatic_client_discovery_signs_and_reuses_database_binding(
    cloud_worker, provider, db_connection, setup_test_db_pool, cashier, till
):
    worker, _ = cloud_worker
    worker.config = provider.config.model_copy(
        update={"clients": {}, "auto_provision_clients": True, "admin_pin": SecretStr("123456")}
    )
    provider.clients.clear()
    async with FiskalyClient(worker.config) as client:
        await worker.configure(db_connection, FiskalySigner(client))
    binding = await db_connection.fetchval(
        "select client_id from fiskaly_client_binding where tse_id=$1 and till_id=$2", worker.tse.id, till.id
    )
    assert binding is not None
    assert str(binding) in provider.created_clients
    assert not provider.admin_authenticated
    assert await db_connection.fetchval("select tse_id from till where id=$1", till.id) == worker.tse.id
    writes = len(provider.created_clients)
    logins = len([request for request in provider.requests if request[1].endswith("/admin/auth")])
    restarted = FiskalyWorker(worker.tse, worker.config)
    order = await booked(db_connection, cashier, till)
    async with FiskalyClient(worker.config) as client:
        signer = FiskalySigner(client)
        await restarted.configure(db_connection, signer)
        await restarted.process(setup_test_db_pool, signer, order.id)
    assert len(provider.created_clients) == writes
    assert len([request for request in provider.requests if request[1].endswith("/admin/auth")]) == logins
    assert await db_connection.fetchval("select signature_status from tse_signature where id=$1", order.id) == "done"
    with pytest.raises(asyncpg.RaiseError, match="immutable"):
        await db_connection.execute(
            "update fiskaly_client_binding set client_id=$3 where tse_id=$1 and till_id=$2",
            worker.tse.id,
            till.id,
            uuid4(),
        )


async def test_lost_client_registration_response_recovers_database_uuid(cloud_worker, provider, db_connection, till):
    worker, _ = cloud_worker
    worker.config = provider.config.model_copy(
        update={
            "clients": {},
            "auto_provision_clients": True,
            "admin_pin": SecretStr("123456"),
            "request_timeout": 0.05,
        }
    )
    provider.clients.clear()
    provider.client_create_timeout = True
    async with FiskalyClient(worker.config) as client:
        with pytest.raises(FiskalyTransportError):
            await worker.configure(db_connection, FiskalySigner(client))
    original = await db_connection.fetchval(
        "select client_id from fiskaly_client_binding where tse_id=$1 and till_id=$2", worker.tse.id, till.id
    )
    assert original is not None
    restarted = FiskalyWorker(worker.tse, worker.config)
    async with FiskalyClient(worker.config) as client:
        await restarted.configure(db_connection, FiskalySigner(client))
    assert (
        await db_connection.fetchval(
            "select client_id from fiskaly_client_binding where tse_id=$1 and till_id=$2 and registered",
            worker.tse.id,
            till.id,
        )
        == original
    )
    assert len(set(provider.created_clients)) == len(provider.created_clients)
    assert str(original) in provider.created_clients


async def test_generated_tss_uuid_is_durable_and_locks_profile(
    cloud_worker, provider, db_connection, event_admin_token, event_node, tmp_path
):
    worker, service = cloud_worker
    worker.config = provider.config.model_copy(
        update={"tss_id": None, "auto_provision_tss": True, "admin_pin": SecretStr("123456"), "puk_directory": tmp_path}
    )
    first = await worker.resolve_config(db_connection)
    assert first.tss_id is not None and first.tss_id.version == 4
    restarted = FiskalyWorker(worker.tse, worker.config)
    assert (await restarted.resolve_config(db_connection)).tss_id == first.tss_id
    assert not provider.requests
    service.config.fiskaly.profiles["replacement"] = provider.config
    with pytest.raises(InvalidArgument, match="cannot change"):
        await service.update_tse(
            token=event_admin_token,
            node_id=event_node.id,
            tse_id=worker.tse.id,
            updated_tse=UpdateTse(name="Cloud", fiskaly_profile="replacement"),
        )
    with pytest.raises(asyncpg.RaiseError, match="immutable"):
        await db_connection.execute("update tse set fiskaly_tss_id=$2 where id=$1", worker.tse.id, uuid4())


async def test_auto_provisioning_validates_event_before_remote_calls(cloud_worker, provider, db_connection):
    worker, _ = cloud_worker
    worker.config = provider.config.model_copy(
        update={"clients": {}, "auto_provision_clients": True, "admin_pin": SecretStr("123456")}
    )
    worker.tse = worker.tse.model_copy(update={"node_id": -1})
    async with FiskalyClient(worker.config) as client:
        with pytest.raises(FiskalyError, match="customer organization"):
            await worker.configure(db_connection, FiskalySigner(client))
    assert not provider.requests


async def test_initialized_tss_is_never_recreated_when_remote_resource_disappears(
    cloud_worker, provider, db_connection, tmp_path
):
    worker, _ = cloud_worker
    async with FiskalyClient(worker.config) as client:
        await worker.configure(db_connection, FiskalySigner(client))
    worker.config = worker.config.model_copy(
        update={"auto_provision_tss": True, "admin_pin": SecretStr("123456"), "puk_directory": tmp_path}
    )
    provider.error_status = 404
    provider.requests.clear()
    async with FiskalyClient(worker.config) as client:
        with pytest.raises(FiskalyHTTPError):
            await worker.configure(db_connection, FiskalySigner(client))
    assert not [request for request in provider.requests if request[0] in {"PUT", "PATCH"}]


async def test_capacity_overflow_preserves_signing_without_rechecking_clients(
    cloud_worker, provider, db_connection, setup_test_db_pool, till_profile, cashier, till
):
    worker, _ = cloud_worker
    worker.config = provider.config.model_copy(
        update={"clients": {}, "auto_provision_clients": True, "admin_pin": SecretStr("123456")}
    )
    provider.clients.clear()
    provider.master["max_number_registered_clients"] = await db_connection.fetchval(
        "select count(*) from till where node_id=$1", till.node_id
    )
    async with FiskalyClient(worker.config) as client:
        signer = FiskalySigner(client)
        await worker.configure(db_connection, signer)
        extra = await db_connection.fetchval(
            "insert into till(node_id,name,description,active_profile_id) values($1,$2,'',$3) returning id",
            till.node_id,
            f"Over capacity {uuid4()}",
            till_profile.id,
        )
        calls = len(provider.requests)
        await worker.configure(db_connection, signer, refresh=True)
        assert len(provider.requests) == calls
        assert await db_connection.fetchval("select tse_id from till where id=$1", extra) is None
        assert not await db_connection.fetchval(
            "select exists(select 1 from fiskaly_client_binding where till_id=$1)", extra
        )
        order = await booked(db_connection, cashier, till)
        await worker.process(setup_test_db_pool, signer, order.id)
    assert await db_connection.fetchval("select signature_status from tse_signature where id=$1", order.id) == "done"
    assert str(extra) in await db_connection.fetchval("select last_error from tse where id=$1", worker.tse.id)


async def test_retry_exhaustion_parks_original_signature_and_allows_later_work(
    cloud_worker, provider, db_connection, setup_test_db_pool, cashier, till
):
    worker, _ = cloud_worker
    first = await booked(db_connection, cashier, till)
    later = await booked(db_connection, cashier, till)
    async with FiskalyClient(worker.config) as client:
        signer = FiskalySigner(client)
        await worker.configure(db_connection, signer)
        original = await worker.prepare(db_connection, first.id)
        await db_connection.execute(
            "update tse_signature set fiskaly_attempts=$2 where id=$1", first.id, MAX_SIGNING_ATTEMPTS - 1
        )
        provider.error_status = 403
        assert await worker.drain(setup_test_db_pool, signer)
        assert await db_connection.fetchval(
            "select fiskaly_next_attempt='infinity' from tse_signature where id=$1", first.id
        )
        provider.error_status = None
        assert await worker.drain(setup_test_db_pool, signer)
        assert not await worker.drain(setup_test_db_pool, signer)
        assert (
            await db_connection.fetchval("select signature_status from tse_signature where id=$1", later.id) == "done"
        )

        await db_connection.execute(
            "update tse_signature set fiskaly_attempts=0,fiskaly_next_attempt=now() "
            "where id=$1 and fiskaly_transaction_id=$2 and fiskaly_next_attempt='infinity'",
            first.id,
            original.transaction_id,
        )
        assert await worker.drain(setup_test_db_pool, signer)
    recovered = await db_connection.fetchrow("select * from tse_signature where id=$1", first.id)
    assert recovered["signature_status"] == "done"
    assert recovered["fiskaly_transaction_id"] == original.transaction_id


@pytest.mark.parametrize("stored_format", ["2026-07-01T12:00:00.123Z", "2026-07-01T12:00:00.123"])
async def test_signed_export_preserves_utc_log_time(
    cloud_worker,
    db_connection,
    setup_test_db_pool,
    cashier,
    till,
    event_node,
    config,
    monkeypatch,
    stored_format,
):
    worker, _ = cloud_worker
    order = await booked(db_connection, cashier, till)
    async with FiskalyClient(worker.config) as client:
        signer = FiskalySigner(client)
        await worker.configure(db_connection, signer)
        await worker.process(setup_test_db_pool, signer, order.id)
    await db_connection.execute("update tse_signature set tse_start=$2,tse_end=$2 where id=$1", order.id, stored_format)
    settings = await fetch_restricted_event_settings_for_node(conn=db_connection, node_id=event_node.id)
    generator = Generator(config, event_node.id, "unused.zip", "unused.xml", "unused.dtd", False)
    try:
        with monkeypatch.context() as local:
            local.setenv("TZ", "Europe/Berlin")
            time.tzset()
            await generator.einzelaufzeichnungsmodul(db_connection, till.z_nr, order.booked_at, till.id, settings)
    finally:
        time.tzset()
    bon = generator.c.records["transactions.csv"][0].data
    logs = generator.c.records["transactions_tse.csv"][0].data
    assert bon["BON_START"] == bon["BON_ENDE"] == "2026-07-01T14:00:00"
    assert logs["TSE_TA_START"] == logs["TSE_TA_ENDE"] == "2026-07-01T12:00:00.123Z"
