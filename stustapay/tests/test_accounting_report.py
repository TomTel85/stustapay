from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from sftkit.database import Connection
from sftkit.error import InvalidArgument

from stustapay.bon.accounting_report import (
    AccountingReportQuery,
    MonthlyDepositProductRow,
    _build_monthly_rows,
    _report_day,
    _resolve_bounds,
    build_accounting_report_context,
    render_accounting_report,
)
from stustapay.bon.pdflatex import PdfRenderResult
from stustapay.bon.report_time import ReportDayMode, is_in_ranges, selected_date_ranges
from stustapay.core.schema.order import OrderType, PaymentMethod
from stustapay.core.schema.tree import Node, PublicEventSettings
from stustapay.core.schema.user import User
from stustapay.core.service.order.booking import NewLineItem, book_order


def _make_event_node() -> Node:
    return Node(
        id=1,
        parent=0,
        name="Festival & Freunde",
        description="",
        read_only=False,
        event=None,
        path="/0/1",
        parent_ids=[0],
        event_node_id=1,
        parents_until_event_node=[],
        forbidden_objects_at_node=[],
        computed_forbidden_objects_at_node=[],
        forbidden_objects_in_subtree=[],
        computed_forbidden_objects_in_subtree=[],
        children=[],
    )


class FakeConnection:
    def __init__(self):
        self.queries: list[str] = []

    async def fetch(self, query: str, *_args):
        self.queries.append(query)
        if "p.is_returnable" in query:
            return []
        if "as booking_day" in query and "donation_exit" in query:
            return []
        if "as account_id" in query:
            return []
        if "p.is_donation" in query:
            return [
                {
                    "booked_at": datetime(2025, 8, 1, 12, tzinfo=timezone.utc),
                    "payment_method": "tag",
                    "node_name": "Agenda",
                    "till_name": "Bar I",
                    "product_name": "Spende",
                    "is_donation": True,
                    "quantity": 2,
                    "amount": Decimal("10.00"),
                },
                {
                    "booked_at": datetime(2025, 8, 1, 13, tzinfo=timezone.utc),
                    "payment_method": "cash",
                    "node_name": "Agenda",
                    "till_name": "Bar I",
                    "product_name": "Pommes",
                    "is_donation": False,
                    "quantity": 4,
                    "amount": Decimal("20.00"),
                },
                {
                    "booked_at": datetime(2025, 8, 1, 14, tzinfo=timezone.utc),
                    "payment_method": "sumup",
                    "node_name": "Pita Police",
                    "till_name": "Containercafe",
                    "product_name": "Pita",
                    "is_donation": False,
                    "quantity": 3,
                    "amount": Decimal("21.00"),
                },
            ]
        if "donation_exit" in query:
            return [
                {
                    "booked_at": datetime(2025, 8, 1, 16, tzinfo=timezone.utc),
                    "amount": Decimal("9.50"),
                },
                {
                    "booked_at": datetime(2025, 8, 3, 16, tzinfo=timezone.utc),
                    "amount": Decimal("99.00"),
                },
            ]
        if "from transaction tr" in query:
            return [
                {
                    "booked_at": datetime(2025, 8, 1, 12, tzinfo=timezone.utc),
                    "order_type": "top_up",
                    "source_type": "cash_entry",
                    "target_type": "cash_register",
                    "amount": Decimal("100.00"),
                },
                {
                    "booked_at": datetime(2025, 8, 1, 13, tzinfo=timezone.utc),
                    "order_type": "sale",
                    "source_type": "cash_entry",
                    "target_type": "cash_register",
                    "amount": Decimal("20.00"),
                },
                {
                    "booked_at": datetime(2025, 8, 1, 14, tzinfo=timezone.utc),
                    "order_type": "pay_out",
                    "source_type": "cash_register",
                    "target_type": "cash_exit",
                    "amount": Decimal("30.00"),
                },
            ]
        if "o.payment_method = 'sumup_online'" in query:
            return [
                {
                    "booked_at": datetime(2025, 8, 1, 15, tzinfo=timezone.utc),
                    "amount": Decimal("50.00"),
                }
            ]
        raise AssertionError(f"Unexpected query: {query}")

    async def fetchval(self, query: str, *_args):
        self.queries.append(query)
        raise AssertionError(f"Unexpected query: {query}")


async def test_build_accounting_report_context_aggregates_accounting_sections(monkeypatch):
    event_node = _make_event_node()
    event = SimpleNamespace(
        start_date=datetime(2025, 8, 1, 6, tzinfo=timezone.utc),
        end_date=datetime(2025, 8, 2, 6, tzinfo=timezone.utc),
        daily_end_time=time(6),
        currency_identifier="EUR",
    )

    async def fake_fetch_event_for_node(**_kwargs):
        return event

    async def fake_fetch_node(**_kwargs):
        return event_node

    monkeypatch.setattr("stustapay.bon.accounting_report.fetch_event_for_node", fake_fetch_event_for_node)
    monkeypatch.setattr("stustapay.bon.accounting_report.fetch_node", fake_fetch_node)
    conn = FakeConnection()

    context = await build_accounting_report_context(
        conn=conn,
        node=event_node,
        query=AccountingReportQuery(selected_dates=["2025-08-01"]),
    )

    assert context.total_revenue == Decimal("51.00")
    assert context.total_cash_topups == Decimal("100.00")
    assert context.total_cash_sales == Decimal("20.00")
    assert context.total_cash_payouts == Decimal("30.00")
    assert context.total_cash_net == Decimal("90.00")
    assert context.total_online_topups == Decimal("50.00")
    assert context.total_product_donations == Decimal("10.00")
    assert context.total_remaining_credit_donations == Decimal("9.50")
    assert context.total_donations == Decimal("19.50")
    assert context.monthly_rows[0].month == "08.2025"
    assert context.daily_cash_rows[0].day == "01.08.2025"
    assert [row.product_name for row in context.donation_product_rows] == ["Spende"]
    assert {row.payment_method for row in context.revenue_rows} == {"Bargeld", "Guthaben/Chip", "SumUp Terminal"}
    assert any("cash_entry" in query and "cash_register" in query for query in conn.queries)
    assert any("not exists" in query and "cancels_order" in query for query in conn.queries)
    assert any("p.type = 'user_defined'" not in query for query in conn.queries if "p.is_donation" in query)

    context.monthly_rows[0].deposit_products = [
        MonthlyDepositProductRow(
            product_id=1234, product_name="Aufladekarte", received=Decimal("25"), refunded=Decimal("5")
        )
    ]
    context.monthly_rows[0].deposit_received = Decimal("25")
    context.monthly_rows[0].deposit_refunded = Decimal("5")

    captured: dict[str, str] = {}

    async def fake_pdflatex(*, file_content: str):
        captured["tex"] = file_content
        return PdfRenderResult(success=True)

    monkeypatch.setattr("stustapay.bon.accounting_report.pdflatex", fake_pdflatex)
    result = await render_accounting_report(context)
    assert result.success is True
    assert "Festival \\& Freunde" in captured["tex"]
    assert "SumUp online" in captured["tex"]
    assert "StuStaPay" not in captured["tex"]
    assert "Interne Kassenbestückungen" not in captured["tex"]
    assert "PayPal" not in captured["tex"]
    assert "2025-08-01" in captured["tex"]
    assert "Kalendertag (00:00 bis 24:00 Uhr)" in captured["tex"]
    assert "anhand ihres Buchungszeitpunkts" in captured["tex"]
    assert "Monatliche Pfand-" in captured["tex"]
    assert "Pfand nach Artikel" in captured["tex"]
    assert "Aufladekarte (ID 1234)" in captured["tex"]


async def test_monthly_accounting_separates_reversals_and_keeps_historical_credit():
    class MonthlyConnection:
        async def fetch(self, query: str, *_args):
            if "p.is_returnable" in query:
                assert "'cancel_sale'" in query
                assert "(li.total_price >= 0)" in query
                return [
                    {
                        "booking_day": date(2025, 7, 31),
                        "product_id": 101,
                        "product_name": "Aufladekarte",
                        "is_returnable": True,
                        "is_donation": False,
                        "amount": Decimal("10"),
                    },
                    {
                        "booking_day": date(2025, 8, 1),
                        "product_id": 101,
                        "product_name": "Aufladekarte",
                        "is_returnable": True,
                        "is_donation": False,
                        "amount": Decimal("-4"),
                    },
                    {
                        "booking_day": date(2025, 8, 1),
                        "product_id": 102,
                        "product_name": "Pfand",
                        "is_returnable": True,
                        "is_donation": False,
                        "amount": Decimal("6"),
                    },
                    {
                        "booking_day": date(2025, 8, 2),
                        "product_id": 103,
                        "product_name": "Spende",
                        "is_returnable": False,
                        "is_donation": True,
                        "amount": Decimal("5"),
                    },
                    {
                        "booking_day": date(2025, 9, 1),
                        "product_id": 101,
                        "product_name": "Aufladekarte",
                        "is_returnable": True,
                        "is_donation": False,
                        "amount": Decimal("-10"),
                    },
                    {
                        "booking_day": date(2025, 9, 1),
                        "product_id": 103,
                        "product_name": "Spende",
                        "is_returnable": False,
                        "is_donation": True,
                        "amount": Decimal("-2"),
                    },
                ]
            if "donation_exit" in query:
                return [
                    {"booking_day": date(2025, 8, 31), "amount": Decimal("3")},
                    {"booking_day": date(2025, 9, 1), "amount": Decimal("-1")},
                ]
            if "as account_id" in query:
                return [
                    {"account_id": 1, "booking_day": date(2025, 7, 31), "amount": Decimal("20")},
                    {"account_id": 2, "booking_day": date(2025, 8, 1), "amount": Decimal("5")},
                    {"account_id": 1, "booking_day": date(2025, 8, 31), "amount": Decimal("-8")},
                    {"account_id": 2, "booking_day": date(2025, 9, 1), "amount": Decimal("-5")},
                    {"account_id": 1, "booking_day": date(2025, 9, 1), "amount": Decimal("-5")},
                ]
            raise AssertionError(query)

    rows = await _build_monthly_rows(
        conn=cast(Connection, MonthlyConnection()),
        event_node_id=1,
        selected_dates=None,
        generated_at=datetime(2025, 9, 15, tzinfo=timezone.utc),
    )
    assert [row.month for row in rows] == ["07.2025", "08.2025", "09.2025"]
    assert [row.remaining_credit for row in rows] == [Decimal("20"), Decimal("17"), Decimal("7")]
    assert rows[0].deposit_received == Decimal("10")
    assert rows[1].deposit_refunded == Decimal("4")
    assert rows[1].deposit_received == Decimal("6")
    assert [(product.product_name, product.received, product.refunded) for product in rows[1].deposit_products] == [
        ("Aufladekarte", Decimal("0"), Decimal("4")),
        ("Pfand", Decimal("6"), Decimal("0")),
    ]
    assert [product.product_id for product in rows[1].deposit_products] == [101, 102]
    assert all(
        sum((product.received for product in row.deposit_products), Decimal("0")) == row.deposit_received
        for row in rows
    )
    assert all(
        sum((product.refunded for product in row.deposit_products), Decimal("0")) == row.deposit_refunded
        for row in rows
    )
    assert rows[2].deposit_refunded == Decimal("10")
    assert rows[1].donations_net == Decimal("8")
    assert rows[2].donations_net == Decimal("-3")
    assert rows[2].provisional is True

    selected = await _build_monthly_rows(
        conn=cast(Connection, MonthlyConnection()),
        event_node_id=1,
        selected_dates=["2025-08-01"],
        generated_at=datetime(2025, 9, 15, tzinfo=timezone.utc),
    )
    assert len(selected) == 1
    assert selected[0].month == "08.2025"
    assert selected[0].remaining_credit == Decimal("17")
    assert selected[0].donation_products_received == Decimal("5")


async def test_monthly_accounting_uses_event_ledger_in_database(
    db_connection: Connection, event_node: Node, global_admin_user: tuple[User, str]
):
    conducting_user = global_admin_user[0]
    private_account = await db_connection.fetchval(
        "insert into account (node_id, type) values ($1, 'private') returning id", event_node.id
    )
    topup_source = await db_connection.fetchval(
        "select id from account where node_id = $1 and type = 'cash_topup_source'", event_node.id
    )
    donation_exit = await db_connection.fetchval(
        "select id from account where node_id = $1 and type = 'donation_exit'", event_node.id
    )
    await db_connection.fetchval(
        "select book_transaction(null, null, $1, $2, 20, 0, $3, $4)",
        topup_source,
        private_account,
        datetime(2025, 7, 31, 21, tzinfo=timezone.utc),
        conducting_user.id,
    )
    await db_connection.fetchval(
        "select book_transaction(null, null, $1, $2, 5, 0, $3, $4)",
        private_account,
        donation_exit,
        datetime(2025, 7, 31, 22, 30, tzinfo=timezone.utc),
        conducting_user.id,
    )

    rows = await _build_monthly_rows(
        conn=db_connection,
        event_node_id=event_node.id,
        selected_dates=["2025-07-01", "2025-08-31"],
        generated_at=datetime(2025, 9, 1, tzinfo=timezone.utc),
    )
    assert [row.month for row in rows] == ["07.2025", "08.2025"]
    assert [row.remaining_credit for row in rows] == [Decimal("20"), Decimal("15")]
    assert rows[1].remaining_credit_donations_received == Decimal("5")
    assert rows[1].remaining_credit == await db_connection.fetchval(
        "select balance from account where id = $1", private_account
    )


async def test_monthly_deposit_products_use_booking_month_in_database(
    db_connection: Connection, event_node: Node, global_admin_user: tuple[User, str]
):
    tax_rate_id = await db_connection.fetchval(
        "select id from tax_rate where node_id = $1 and name = 'none'", event_node.id
    )
    till_id = await db_connection.fetchval("select id from till where node_id = $1 and is_virtual", event_node.id)
    card_product_id = await db_connection.fetchval(
        "insert into product (type, name, price, fixed_price, is_returnable, tax_rate_id, node_id) "
        "values ('user_defined', 'Aufladekarte', 5, true, true, $1, $2) returning id",
        tax_rate_id,
        event_node.id,
    )
    other_product_id = await db_connection.fetchval(
        "insert into product (type, name, price, fixed_price, is_returnable, tax_rate_id, node_id) "
        "values ('user_defined', 'Pfand', 2, true, true, $1, $2) returning id",
        tax_rate_id,
        event_node.id,
    )
    original = await book_order(
        conn=db_connection,
        order_type=OrderType.sale,
        payment_method=PaymentMethod.tag,
        cashier_id=global_admin_user[0].id,
        till_id=till_id,
        line_items=[NewLineItem(quantity=2, product_id=card_product_id, product_price=5, tax_rate_id=tax_rate_id)],
        bookings={},
        booked_at=datetime(2025, 7, 31, 21, tzinfo=timezone.utc),
    )
    await book_order(
        conn=db_connection,
        order_type=OrderType.cancel_sale,
        payment_method=PaymentMethod.tag,
        cashier_id=global_admin_user[0].id,
        till_id=till_id,
        line_items=[NewLineItem(quantity=-2, product_id=card_product_id, product_price=5, tax_rate_id=tax_rate_id)],
        bookings={},
        cancels_order=original.id,
        booked_at=datetime(2025, 7, 31, 22, 30, tzinfo=timezone.utc),
    )
    await book_order(
        conn=db_connection,
        order_type=OrderType.sale,
        payment_method=PaymentMethod.tag,
        cashier_id=global_admin_user[0].id,
        till_id=till_id,
        line_items=[NewLineItem(quantity=3, product_id=other_product_id, product_price=2, tax_rate_id=tax_rate_id)],
        bookings={},
        booked_at=datetime(2025, 8, 1, 12, tzinfo=timezone.utc),
    )

    rows = await _build_monthly_rows(
        conn=db_connection,
        event_node_id=event_node.id,
        selected_dates=["2025-07-31", "2025-08-01"],
        generated_at=datetime(2025, 9, 1, tzinfo=timezone.utc),
    )
    assert [(row.month, row.deposit_received, row.deposit_refunded) for row in rows] == [
        ("07.2025", Decimal("10"), Decimal("0")),
        ("08.2025", Decimal("6"), Decimal("10")),
    ]
    assert [(product.product_name, product.received, product.refunded) for product in rows[1].deposit_products] == [
        ("Aufladekarte", Decimal("0"), Decimal("10")),
        ("Pfand", Decimal("6"), Decimal("0")),
    ]


def test_report_day_uses_event_boundary_in_berlin_timezone():
    assert _report_day(datetime(2025, 8, 1, 3, tzinfo=timezone.utc), time(6), ReportDayMode.EVENT_DAY) == "31.07.2025"
    assert _report_day(datetime(2025, 8, 1, 4, tzinfo=timezone.utc), time(6), ReportDayMode.EVENT_DAY) == "01.08.2025"
    assert (
        _report_day(datetime(2025, 8, 1, 3, tzinfo=timezone.utc), time(6), ReportDayMode.CALENDAR_DAY) == "01.08.2025"
    )


def test_selected_date_ranges_use_berlin_time_and_half_open_dst_boundaries():
    summer = selected_date_ranges(["2025-08-01"], day_mode=ReportDayMode.CALENDAR_DAY, daily_end_time=time(6))
    assert summer == [
        (
            datetime(2025, 7, 31, 22, tzinfo=timezone.utc),
            datetime(2025, 8, 1, 22, tzinfo=timezone.utc),
        )
    ]

    dst_change = selected_date_ranges(["2025-10-26"], day_mode=ReportDayMode.CALENDAR_DAY, daily_end_time=time(6))
    assert dst_change == [
        (
            datetime(2025, 10, 25, 22, tzinfo=timezone.utc),
            datetime(2025, 10, 26, 23, tzinfo=timezone.utc),
        )
    ]

    non_contiguous = selected_date_ranges(
        ["2025-08-01", "2025-08-03"],
        day_mode=ReportDayMode.CALENDAR_DAY,
        daily_end_time=time(6),
    )
    assert is_in_ranges(datetime(2025, 8, 1, 21, 59, tzinfo=timezone.utc), non_contiguous)
    assert not is_in_ranges(datetime(2025, 8, 1, 22, tzinfo=timezone.utc), non_contiguous)
    assert not is_in_ranges(datetime(2025, 8, 2, 12, tzinfo=timezone.utc), non_contiguous)


def test_event_day_requires_a_configured_daily_end_time():
    with pytest.raises(InvalidArgument, match="daily end time"):
        selected_date_ranges(["2025-08-01"], day_mode=ReportDayMode.EVENT_DAY, daily_end_time=None)
    with pytest.raises(InvalidArgument, match="daily end time"):
        selected_date_ranges(None, day_mode=ReportDayMode.EVENT_DAY, daily_end_time=None)


def test_unfiltered_accounting_report_uses_the_same_all_time_bounds_as_statistics():
    event = SimpleNamespace(
        start_date=datetime(2025, 8, 1, 6, tzinfo=timezone.utc),
        end_date=datetime(2025, 8, 2, 6, tzinfo=timezone.utc),
        daily_end_time=time(6),
    )

    from_time, to_time = _resolve_bounds(AccountingReportQuery(), cast(PublicEventSettings, event))

    assert from_time == datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert to_time == datetime(4000, 1, 1, tzinfo=timezone.utc)
