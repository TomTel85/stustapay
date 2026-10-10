# ruff: noqa: F811
"""Two independently prepared tills importing sales after a shared outage."""

from decimal import Decimal

import pytest

from stustapay.core.schema.offline import OfflineBooking, OfflineBookingStatus, OfflineImport
from stustapay.tests.terminal.test_offline import sale_for
from stustapay.tests.terminal.test_sale import sale_products  # noqa: F401


@pytest.mark.parametrize("arrival_order", [(0, 1), (1, 0)])
async def test_two_offline_terminals_reconcile_shared_customer_once(
    arrival_order,
    order_service,
    terminal_service,
    terminal_token,
    create_terminal_token,
    customer,
    sale_products,
    till,
    cashier,
    login_supervised_user,
    db_connection,
    event_node,
):
    """Both tills see the same balance, then independently spend it while disconnected."""
    second_token = await create_terminal_token()
    second_config = await terminal_service.get_terminal_config(token=second_token)
    await db_connection.execute(
        "update till set active_profile_id=$1 where id=$2", till.active_profile_id, second_config.till.id
    )
    await db_connection.execute("update event set offline_enabled=true where id=$1", event_node.event.id)
    await db_connection.execute("update account set balance=7 where id=$1", customer.account_id)

    tokens = (terminal_token, second_token)
    snapshots = []
    for token in tokens:
        await login_supervised_user(
            user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id, terminal_token=token
        )
        snapshots.append(await order_service.prepare_offline(token=token))

    assert snapshots[0].id != snapshots[1].id
    assert all(
        next(c for c in snapshot.customers if c.customer_tag_uid == customer.tag.uid).balance_cents == 700
        for snapshot in snapshots
    )

    sales = [sale_for(customer, sale_products) for _ in tokens]
    bookings = [
        OfflineBooking(snapshot_id=snapshot.id, sale=sale, sequence=1, recorded_at=snapshot.server_time)
        for snapshot, sale in zip(snapshots, sales, strict=True)
    ]
    for index in arrival_order:
        result = await order_service.import_offline(
            token=tokens[index], payload=OfflineImport(bookings=[bookings[index]])
        )
        assert result.results[0].status == OfflineBookingStatus.booked
        assert result.results[0].sale.uuid == sales[index].uuid

    assert await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == Decimal(-3)
    assert (
        await db_connection.fetchval(
            "select count(*) from ordr where uuid=any($1::uuid[])", [sale.uuid for sale in sales]
        )
        == 2
    )

    for index in reversed(arrival_order):
        replay = await order_service.import_offline(
            token=tokens[index], payload=OfflineImport(bookings=[bookings[index]])
        )
        assert replay.results[0].status == OfflineBookingStatus.already_booked
    assert await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == Decimal(-3)
