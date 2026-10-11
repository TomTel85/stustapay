# ruff: noqa: F811
# pylint: disable=redefined-outer-name,unused-argument,unused-import,missing-kwoa
"""Report reads stay bounded to the customers needed for unfinished sales."""

from datetime import timedelta

from stustapay.core.schema.offline import OfflineBooking, OfflineImport, OfflineSnapshot
from stustapay.tests.terminal.test_offline import prepared_offline, sale_for  # noqa: F401
from stustapay.tests.terminal.test_sale import sale_products  # noqa: F401


async def test_completed_offline_report_needs_no_snapshot(
    prepared_offline, order_service, terminal_token, customer, sale_products, event_admin_token, event_node, monkeypatch
):
    snapshot = prepared_offline
    sale = sale_for(customer, sale_products)
    await order_service.import_offline(
        token=terminal_token,
        payload=OfflineImport(
            bookings=[OfflineBooking(snapshot_id=snapshot.id, sale=sale, sequence=1, recorded_at=snapshot.server_time)]
        ),
    )

    def forbid_snapshot(*_args, **_kwargs):
        raise AssertionError("Completed report must use its stored sale, not reload the event's customers")

    monkeypatch.setattr(OfflineSnapshot, "model_validate", forbid_snapshot)
    report = await order_service.offline_report(token=event_admin_token, node_id=event_node.id)
    assert len(report) == 1
    assert report[0].customer_account_id == customer.account_id
    assert report[0].amount_cents == 500


async def test_unfinished_report_loads_only_relevant_customers_once(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    event_admin_token,
    event_node,
    db_connection,
    monkeypatch,
):
    snapshot = prepared_offline
    sales = [sale_for(customer, sale_products) for _ in range(2)]
    await order_service.import_offline(
        token=terminal_token,
        payload=OfflineImport(
            bookings=[
                OfflineBooking(
                    snapshot_id=snapshot.id,
                    sale=sale,
                    sequence=i + 1,
                    recorded_at=snapshot.valid_until + timedelta(seconds=1),
                )
                for i, sale in enumerate(sales)
            ]
        ),
    )
    # A large catalog must not be returned or modelled for every report row.
    relevant = next(c for c in snapshot.customers if c.customer_tag_uid == customer.tag.uid)
    stored = snapshot.model_dump(mode="json")
    stored["customers"] = [relevant.model_dump(mode="json")] + [
        {"customer_account_id": 100000 + i, "customer_tag_uid": 100000 + i, "balance_cents": 1000, "restriction": None}
        for i in range(1000)
    ]
    await db_connection.execute("update terminal_offline_snapshot set snapshot=$2 where id=$1", snapshot.id, stored)
    parsed_customer_counts = []
    original = OfflineSnapshot.model_validate

    def capture_snapshot(value, **kwargs):
        parsed_customer_counts.append(len(value["customers"]))
        return original(value, **kwargs)

    monkeypatch.setattr(OfflineSnapshot, "model_validate", capture_snapshot)
    report = await order_service.offline_report(token=event_admin_token, node_id=event_node.id)
    assert len(report) == 2
    assert parsed_customer_counts == [1]
    assert all(row.customer_account_id == customer.account_id and row.amount_cents == 500 for row in report)
