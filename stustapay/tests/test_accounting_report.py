from datetime import datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from sftkit.error import InvalidArgument

from stustapay.bon.accounting_report import (
    AccountingReportQuery,
    _report_day,
    _resolve_bounds,
    build_accounting_report_context,
    render_accounting_report,
)
from stustapay.bon.pdflatex import PdfRenderResult
from stustapay.bon.report_time import ReportDayMode, is_in_ranges, selected_date_ranges
from stustapay.core.schema.tree import Node, PublicEventSettings


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
    assert context.daily_cash_rows[0].day == "01.08.2025"
    assert [row.product_name for row in context.donation_product_rows] == ["Spende"]
    assert {row.payment_method for row in context.revenue_rows} == {"Bargeld", "Guthaben/Chip", "SumUp Terminal"}
    assert any("cash_entry" in query and "cash_register" in query for query in conn.queries)
    assert any("not exists" in query and "cancels_order" in query for query in conn.queries)
    assert any("p.type = 'user_defined'" not in query for query in conn.queries if "p.is_donation" in query)

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
