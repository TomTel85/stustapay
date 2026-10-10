# ruff: noqa: F811
# pylint: disable=redefined-outer-name,unused-argument,unexpected-keyword-arg,unused-import,missing-kwoa
"""Real transaction tests for automatic recovery without a second financial booking."""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from asyncpg import ForeignKeyViolationError
from sftkit.error import InvalidArgument, ServiceException

from stustapay.core.schema.offline import OfflineBooking, OfflineBookingStatus, OfflineImport
from stustapay.core.service.order import offline
from stustapay.tests.terminal.test_offline import prepared_offline, sale_for  # noqa: F401
from stustapay.tests.terminal.test_sale import sale_products  # noqa: F401


def booking_for(snapshot, customer, products):
    return OfflineBooking(
        snapshot_id=snapshot.id, sale=sale_for(customer, products), sequence=1, recorded_at=snapshot.server_time
    )


async def fail_after_financial_write(monkeypatch, exception):
    original = offline.make_sale_bookings

    async def interrupted(**kwargs):
        await original(**kwargs)
        raise exception

    monkeypatch.setattr(offline, "make_sale_bookings", interrupted)
    return original


async def test_transient_failure_rolls_back_then_worker_settles_once(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    db_connection,
    monkeypatch,
    event_admin_token,
    event_node,
):
    booking = booking_for(prepared_offline, customer, sale_products)
    initial = await db_connection.fetchval("select balance from account where id=$1", customer.account_id)
    await db_connection.execute(
        "update terminal_offline_snapshot set last_contact_at='2000-01-01' where id=$1", prepared_offline.id
    )
    original = await fail_after_financial_write(
        monkeypatch, ServiceException("Temporary booking dependency unavailable")
    )
    first = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert first.results[0].status == OfflineBookingStatus.retry_required
    with pytest.raises(InvalidArgument, match="Pending offline reconciliation"):
        await order_service.prepare_offline(token=terminal_token)
    assert await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == initial
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 0
    report = await order_service.offline_report(token=event_admin_token, node_id=event_node.id)
    row = next(r for r in report if r.uuid == booking.sale.uuid)
    assert row.amount_cents == 500
    assert row.customer_account_id == customer.account_id
    assert row.customer_tag_uid == customer.tag.uid
    assert row.buttons == booking.sale.buttons
    assert row.attempt_count == 1
    monkeypatch.setattr(offline, "make_sale_bookings", original)
    last_contact = await db_connection.fetchval(
        "select last_contact_at from terminal_offline_snapshot where id=$1", prepared_offline.id
    )
    assert last_contact.year != 2000
    await order_service.reconcile_pending_offline()
    await order_service.reconcile_pending_offline()
    assert await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == initial - 5
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 1
    persisted = await db_connection.fetchrow("select * from terminal_offline_import where uuid=$1", booking.sale.uuid)
    assert persisted["result"]["status"] == "booked"
    assert persisted["attempt_count"] == 2
    assert (
        await db_connection.fetchval(
            "select last_contact_at from terminal_offline_snapshot where id=$1", prepared_offline.id
        )
        == last_contact
    )
    assert (await order_service.prepare_offline(token=terminal_token)).id != prepared_offline.id


async def test_worker_and_device_replay_cannot_double_book(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    db_connection,
    monkeypatch,
):
    booking = booking_for(prepared_offline, customer, sale_products)
    initial = await db_connection.fetchval("select balance from account where id=$1", customer.account_id)
    original = await fail_after_financial_write(monkeypatch, ServiceException("Temporary failure"))
    await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    monkeypatch.setattr(offline, "make_sale_bookings", original)
    await asyncio.gather(
        order_service.reconcile_pending_offline(),
        order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking])),
    )
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 1
    assert await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == initial - 5


async def test_status_rechecks_previous_clarification_after_dependency_recovery(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    db_connection,
    monkeypatch,
):
    booking = booking_for(prepared_offline, customer, sale_products)
    original = await fail_after_financial_write(monkeypatch, InvalidArgument("Dependency changed"))
    first = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert first.results[0].status == OfflineBookingStatus.clarification_required
    monkeypatch.setattr(offline, "make_sale_bookings", original)
    recovered = await order_service.offline_booking_status(token=terminal_token, order_uuid=booking.sale.uuid)
    assert recovered.status == OfflineBookingStatus.booked
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 1
    assert (await order_service.prepare_offline(token=terminal_token)).id != prepared_offline.id


async def test_worker_settles_persisted_sale_after_terminal_retirement(
    prepared_offline,
    order_service,
    terminal_token,
    terminal_service,
    terminal,
    customer,
    sale_products,
    db_connection,
    monkeypatch,
    event_admin_token,
    event_node,
):
    booking = booking_for(prepared_offline, customer, sale_products)
    original = await fail_after_financial_write(monkeypatch, ServiceException("Temporary failure"))
    await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    monkeypatch.setattr(offline, "make_sale_bookings", original)
    await db_connection.execute("update till set terminal_id=null where terminal_id=$1", terminal.id)
    await terminal_service.delete_terminal(token=event_admin_token, node_id=event_node.id, terminal_id=terminal.id)
    await order_service.reconcile_pending_offline()
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 1
    assert (
        await db_connection.fetchval(
            "select result->>'status' from terminal_offline_import where uuid=$1", booking.sale.uuid
        )
        == "booked"
    )


async def test_future_timestamp_waits_for_clock_without_manual_clarification(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    db_connection,
    monkeypatch,
):
    booking = booking_for(prepared_offline, customer, sale_products)
    booking.recorded_at = prepared_offline.server_time + timedelta(seconds=60)
    first = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert first.results[0].status == OfflineBookingStatus.retry_required

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return booking.recorded_at + timedelta(seconds=1)

    monkeypatch.setattr(offline, "datetime", Later)
    await order_service.reconcile_pending_offline()
    assert (
        await db_connection.fetchval(
            "select result->>'status' from terminal_offline_import where uuid=$1", booking.sale.uuid
        )
        == "booked"
    )


async def test_conflicting_uuid_never_inherits_receipt_or_duplicates_rejection(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    db_connection,
    event_admin_token,
    event_node,
):
    booking = booking_for(prepared_offline, customer, sale_products)
    await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    conflict = booking.model_copy(deep=True)
    conflict.sale.buttons[0].quantity = 2
    for _ in range(2):
        result = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[conflict]))
        assert result.results[0].status == OfflineBookingStatus.clarification_required
    status = await order_service.offline_booking_status(token=terminal_token, order_uuid=booking.sale.uuid)
    assert status.status == OfflineBookingStatus.clarification_required
    assert status.sale is None
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 1
    assert (
        await db_connection.fetchval(
            "select count(*) from terminal_offline_rejection where request->'sale'->>'uuid'=$1", str(booking.sale.uuid)
        )
        == 1
    )
    await order_service.dismiss_offline(token=event_admin_token, node_id=event_node.id, order_uuid=booking.sale.uuid)
    dismissed = await order_service.offline_booking_status(token=terminal_token, order_uuid=booking.sale.uuid)
    assert dismissed.status == OfflineBookingStatus.dismissed
    assert dismissed.sale is None


async def test_status_recovers_restored_authorization_and_resolves_original_rejection(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    db_connection,
    event_admin_token,
    event_node,
):
    booking = booking_for(prepared_offline, customer, sale_products)
    booking.snapshot_id = uuid4()
    first = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert first.results[0].status == OfflineBookingStatus.clarification_required
    await db_connection.execute(
        "update terminal_offline_snapshot set id=$2,snapshot=jsonb_set(snapshot,'{id}',to_jsonb($2::uuid::text)) where id=$1",
        prepared_offline.id,
        booking.snapshot_id,
    )
    recovered = await order_service.offline_booking_status(token=terminal_token, order_uuid=booking.sale.uuid)
    assert recovered.status == OfflineBookingStatus.booked
    assert await db_connection.fetchval(
        "select resolved_at is not null from terminal_offline_rejection where request->'sale'->>'uuid'=$1",
        str(booking.sale.uuid),
    )
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 1
    assert (await order_service.prepare_offline(token=terminal_token)).id != booking.snapshot_id
    report = await order_service.offline_report(token=event_admin_token, node_id=event_node.id)
    assert {row.status for row in report if row.uuid == booking.sale.uuid} == {OfflineBookingStatus.booked}


async def test_read_only_event_allows_audited_dismissal_of_invalid_sale(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    db_connection,
    event_admin_token,
    event_node,
):
    booking = booking_for(prepared_offline, customer, sale_products)
    booking.recorded_at = prepared_offline.valid_until + timedelta(seconds=1)
    first = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert first.results[0].status == OfflineBookingStatus.clarification_required
    await db_connection.execute("update node set read_only=true where id=$1", event_node.id)
    await order_service.dismiss_offline(token=event_admin_token, node_id=event_node.id, order_uuid=booking.sale.uuid)
    status = await order_service.offline_booking_status(token=terminal_token, order_uuid=booking.sale.uuid)
    assert status.status == OfflineBookingStatus.dismissed
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 0


@pytest.mark.parametrize(
    "failure", [InvalidArgument("Original dependency missing"), ForeignKeyViolationError("Missing reference")]
)
async def test_worker_rechecks_repaired_clarification_without_device_contact(
    prepared_offline, order_service, terminal_token, customer, sale_products, db_connection, monkeypatch, failure
):
    booking = booking_for(prepared_offline, customer, sale_products)
    original = await fail_after_financial_write(monkeypatch, failure)
    await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    monkeypatch.setattr(offline, "make_sale_bookings", original)
    await db_connection.execute(
        "update terminal_offline_import set last_attempt_at=now()-interval '6 minutes' where uuid=$1",
        booking.sale.uuid,
    )
    await order_service.reconcile_pending_offline()
    assert (
        await db_connection.fetchval(
            "select result->>'status' from terminal_offline_import where uuid=$1", booking.sale.uuid
        )
        == "booked"
    )
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 1


async def test_worker_recovers_restored_snapshot_without_device_contact(
    prepared_offline, order_service, terminal_token, customer, sale_products, db_connection
):
    booking = booking_for(prepared_offline, customer, sale_products)
    booking.snapshot_id = uuid4()
    await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    await db_connection.execute(
        "update terminal_offline_snapshot set id=$2,snapshot=jsonb_set(snapshot,'{id}',to_jsonb($2::uuid::text)) where id=$1",
        prepared_offline.id,
        booking.snapshot_id,
    )
    await db_connection.execute("update terminal_offline_rejection set last_attempt_at=now()-interval '6 minutes'")
    await order_service.reconcile_pending_offline()
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 1
    assert await db_connection.fetchval(
        "select resolved_at is not null from terminal_offline_rejection where request->'sale'->>'uuid'=$1",
        str(booking.sale.uuid),
    )


async def test_legacy_receipt_rejects_duplicate_positions_with_different_total(
    prepared_offline, order_service, terminal_token, customer, sale_products, db_connection
):
    booking = booking_for(prepared_offline, customer, sale_products)
    booked = await order_service.book_sale(token=terminal_token, new_sale=booking.sale)
    await db_connection.execute("delete from terminal_sale_journal where uuid=$1", booking.sale.uuid)
    await db_connection.execute(
        "insert into line_item(order_id,item_id,product_id,product_price,quantity,tax_name,tax_rate,tax_rate_id) "
        "select order_id,9999,product_id,product_price,quantity,tax_name,tax_rate,tax_rate_id "
        "from line_item where order_id=$1 order by item_id limit 1",
        booked.id,
    )
    balance = await db_connection.fetchval("select balance from account where id=$1", customer.account_id)
    result = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert result.results[0].status == OfflineBookingStatus.clarification_required
    assert result.results[0].sale is None
    assert await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == balance
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 1


async def test_conflicting_online_uuid_status_cannot_confirm_different_offline_sale(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    db_connection,
    event_admin_token,
    event_node,
):
    booking = booking_for(prepared_offline, customer, sale_products)
    original = await order_service.book_sale(token=terminal_token, new_sale=booking.sale)
    booking.sale.buttons[0].quantity = 2
    imported = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert imported.results[0].status == OfflineBookingStatus.clarification_required
    status = await order_service.offline_booking_status(token=terminal_token, order_uuid=booking.sale.uuid)
    assert status.status == OfflineBookingStatus.clarification_required
    assert status.sale is None
    await order_service.dismiss_offline(token=event_admin_token, node_id=event_node.id, order_uuid=booking.sale.uuid)
    status = await order_service.offline_booking_status(token=terminal_token, order_uuid=booking.sale.uuid)
    assert status.status == OfflineBookingStatus.dismissed
    assert status.sale is None
    assert (
        await db_connection.fetchval("select balance from account where id=$1", customer.account_id)
        == original.new_balance
    )
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", booking.sale.uuid) == 1
