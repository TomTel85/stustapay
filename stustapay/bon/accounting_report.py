from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytz
from pydantic import BaseModel
from sftkit.database import Connection
from sftkit.error import InvalidArgument

from stustapay.bon.pdflatex import PdfRenderResult, pdflatex, render_template
from stustapay.core.currency import get_currency_symbol
from stustapay.core.schema.tree import Node, PublicEventSettings
from stustapay.core.service.order.stats import TimeseriesStatsQuery, get_event_time_bounds, get_selected_date_ranges
from stustapay.core.service.tree.common import fetch_event_for_node, fetch_node

REPORT_TIMEZONE = pytz.timezone("Europe/Berlin")
ZERO = Decimal("0")


class AccountingReportQuery(BaseModel):
    from_time: datetime | None = None
    to_time: datetime | None = None
    till_id: int | None = None
    subnode_id: int | None = None
    selected_dates: list[str] | None = None


class RevenueSummaryRow(BaseModel):
    node_name: str
    till_name: str
    payment_method: str
    amount: Decimal


class ProductSummaryRow(BaseModel):
    node_name: str
    till_name: str
    product_name: str
    payment_method: str
    quantity: int
    amount: Decimal
    is_donation: bool


class DailyCashRow(BaseModel):
    day: str
    cash_topups: Decimal = ZERO
    cash_sales: Decimal = ZERO
    cash_payouts: Decimal = ZERO
    net_amount: Decimal = ZERO


class DailyOnlineTopUpRow(BaseModel):
    day: str
    amount: Decimal = ZERO


class AccountingReportContext(BaseModel):
    event_name: str
    scope_name: str
    till_name: str | None
    generated_at: datetime
    from_time: datetime
    to_time: datetime
    includes_all_event_bookings: bool
    daily_end_time: time | None
    selected_dates: list[str]
    currency_symbol: str
    revenue_rows: list[RevenueSummaryRow]
    product_rows: list[ProductSummaryRow]
    donation_product_rows: list[ProductSummaryRow]
    daily_cash_rows: list[DailyCashRow]
    daily_online_topup_rows: list[DailyOnlineTopUpRow]
    total_revenue: Decimal
    total_cash_topups: Decimal
    total_cash_sales: Decimal
    total_cash_payouts: Decimal
    total_cash_net: Decimal
    total_online_topups: Decimal
    total_product_donations: Decimal
    total_remaining_credit_donations: Decimal
    total_donations: Decimal
    includes_remaining_credit_donations: bool


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _resolve_bounds(query: AccountingReportQuery, event: PublicEventSettings) -> tuple[datetime, datetime]:
    stats_query = TimeseriesStatsQuery(
        from_time=query.from_time,
        to_time=query.to_time,
        till_id=query.till_id,
        subnode_id=query.subnode_id,
        selected_dates=query.selected_dates,
    )
    return get_event_time_bounds(stats_query, event)


def _is_in_selected_ranges(value: datetime, selected_ranges: list[tuple[datetime, datetime]]) -> bool:
    if not selected_ranges:
        return True
    normalized = _normalize_datetime(value)
    return any(_normalize_datetime(start) <= normalized <= _normalize_datetime(end) for start, end in selected_ranges)


def _report_day(value: datetime, daily_end_time: time | None) -> str:
    local = _normalize_datetime(value).astimezone(REPORT_TIMEZONE)
    if daily_end_time is not None and local.timetz().replace(tzinfo=None) < daily_end_time:
        local -= timedelta(days=1)
    return local.strftime("%d.%m.%Y")


def _payment_method_label(payment_method: str) -> str:
    return {
        "cash": "Bargeld",
        "sumup": "SumUp Terminal",
        "sumup_online": "SumUp online",
        "tag": "Guthaben/Chip",
    }.get(payment_method, payment_method)


async def _resolve_scope_node(conn: Connection, root_node: Node, subnode_id: int | None) -> Node:
    if subnode_id is None or subnode_id == root_node.id:
        return root_node
    scope_node = await fetch_node(conn=conn, node_id=subnode_id)
    if scope_node is None or (root_node.id != scope_node.id and root_node.id not in scope_node.parent_ids):
        raise InvalidArgument("Selected subnode is outside the report scope")
    if scope_node.event_node_id != root_node.event_node_id:
        raise InvalidArgument("Selected subnode belongs to another event")
    return scope_node


async def _fetch_till_name(conn: Connection, scope_node: Node, till_id: int | None) -> str | None:
    if till_id is None:
        return None
    till_name = await conn.fetchval(
        "select t.name from till t join node n on n.id = t.node_id "
        "where t.id = $1 and ($2 = any(n.parent_ids) or n.id = $2)",
        till_id,
        scope_node.id,
    )
    if till_name is None:
        raise InvalidArgument("Selected till is outside the report scope")
    return till_name


async def build_accounting_report_context(
    conn: Connection, node: Node, query: AccountingReportQuery
) -> AccountingReportContext:
    if node.event_node_id is None:
        raise InvalidArgument("Accounting reports require an event node")

    scope_node = await _resolve_scope_node(conn=conn, root_node=node, subnode_id=query.subnode_id)
    event = await fetch_event_for_node(conn=conn, node=scope_node)
    event_node = await fetch_node(conn=conn, node_id=node.event_node_id)
    assert event_node is not None
    till_name = await _fetch_till_name(conn=conn, scope_node=scope_node, till_id=query.till_id)
    from_time, to_time = _resolve_bounds(query=query, event=event)
    stats_query = TimeseriesStatsQuery(
        from_time=query.from_time,
        to_time=query.to_time,
        till_id=query.till_id,
        subnode_id=query.subnode_id,
        selected_dates=query.selected_dates,
    )
    selected_ranges = get_selected_date_ranges(stats_query, event)

    sales_rows = await conn.fetch(
        "select o.booked_at, o.payment_method, n.name as node_name, t.name as till_name, "
        "p.name as product_name, p.is_donation, sum(li.quantity)::bigint as quantity, "
        "round(sum(li.total_price), 2) as amount "
        "from ordr o "
        "join till t on t.id = o.till_id "
        "join node n on n.id = t.node_id "
        "join line_item li on li.order_id = o.id "
        "join product p on p.id = li.product_id "
        "where ($3 = any(n.parent_ids) or n.id = $3) "
        "and o.booked_at >= $1 and o.booked_at <= $2 "
        "and ($4::bigint is null or o.till_id = $4) "
        "and o.order_type = 'sale' "
        "and not exists (select 1 from ordr c where c.cancels_order = o.id) "
        "group by o.booked_at, o.payment_method, n.id, n.name, t.id, t.name, p.id, p.name, p.is_donation "
        "order by n.name, t.name, p.name, o.payment_method, o.booked_at",
        from_time,
        to_time,
        scope_node.id,
        query.till_id,
    )
    cash_rows = await conn.fetch(
        "select tr.booked_at, o.order_type, sa.type as source_type, ta.type as target_type, tr.amount "
        "from transaction tr "
        "join ordr o on o.id = tr.order_id "
        "join till t on t.id = o.till_id "
        "join node n on n.id = t.node_id "
        "join account sa on sa.id = tr.source_account "
        "join account ta on ta.id = tr.target_account "
        "where ($3 = any(n.parent_ids) or n.id = $3) "
        "and tr.booked_at >= $1 and tr.booked_at <= $2 "
        "and ($4::bigint is null or o.till_id = $4) "
        "and ((sa.type = 'cash_entry' and ta.type = 'cash_register') "
        "or (sa.type = 'cash_register' and ta.type = 'cash_exit' and o.order_type = 'pay_out')) "
        "order by tr.booked_at",
        from_time,
        to_time,
        scope_node.id,
        query.till_id,
    )
    online_rows = await conn.fetch(
        "select o.booked_at, round(sum(li.total_price), 2) as amount "
        "from ordr o "
        "join till t on t.id = o.till_id "
        "join node n on n.id = t.node_id "
        "join line_item li on li.order_id = o.id "
        "where ($3 = any(n.parent_ids) or n.id = $3) "
        "and o.booked_at >= $1 and o.booked_at <= $2 "
        "and ($4::bigint is null or o.till_id = $4) "
        "and o.order_type = 'top_up' and o.payment_method = 'sumup_online' "
        "group by o.id, o.booked_at order by o.booked_at",
        from_time,
        to_time,
        scope_node.id,
        query.till_id,
    )
    includes_remaining_credit_donations = node.id == node.event_node_id
    remaining_credit_donations = ZERO
    if includes_remaining_credit_donations:
        remaining_credit_donations = await conn.fetchval(
            "select coalesce(round(sum(tr.amount), 2), 0) "
            "from transaction tr "
            "join account sa on sa.id = tr.source_account "
            "join account ta on ta.id = tr.target_account "
            "where sa.type = 'private' and ta.type = 'donation_exit' and ta.node_id = $1",
            node.event_node_id,
        )

    product_aggregation: dict[tuple[str, str, str, str, bool], tuple[int, Decimal]] = {}
    revenue_aggregation: dict[tuple[str, str, str], Decimal] = defaultdict(lambda: ZERO)
    for row in sales_rows:
        if not _is_in_selected_ranges(row["booked_at"], selected_ranges):
            continue
        payment_label = _payment_method_label(row["payment_method"])
        product_key = (
            row["node_name"],
            row["till_name"],
            row["product_name"],
            payment_label,
            row["is_donation"],
        )
        quantity, amount = product_aggregation.get(product_key, (0, ZERO))
        product_aggregation[product_key] = (quantity + row["quantity"], amount + row["amount"])
        revenue_aggregation[(row["node_name"], row["till_name"], payment_label)] += row["amount"]

    product_rows = [
        ProductSummaryRow(
            node_name=key[0],
            till_name=key[1],
            product_name=key[2],
            payment_method=key[3],
            is_donation=key[4],
            quantity=value[0],
            amount=value[1],
        )
        for key, value in sorted(product_aggregation.items())
    ]
    revenue_rows = [
        RevenueSummaryRow(node_name=key[0], till_name=key[1], payment_method=key[2], amount=value)
        for key, value in sorted(revenue_aggregation.items())
    ]

    daily_cash: dict[str, DailyCashRow] = {}
    for row in cash_rows:
        if not _is_in_selected_ranges(row["booked_at"], selected_ranges):
            continue
        day = _report_day(row["booked_at"], event.daily_end_time)
        daily = daily_cash.setdefault(day, DailyCashRow(day=day))
        if row["source_type"] == "cash_entry" and row["order_type"] == "top_up":
            daily.cash_topups += row["amount"]
        elif row["source_type"] == "cash_entry":
            daily.cash_sales += row["amount"]
        elif row["target_type"] == "cash_exit" and row["order_type"] == "pay_out":
            daily.cash_payouts += row["amount"]
        daily.net_amount = daily.cash_topups + daily.cash_sales - daily.cash_payouts

    daily_online: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in online_rows:
        if _is_in_selected_ranges(row["booked_at"], selected_ranges):
            daily_online[_report_day(row["booked_at"], event.daily_end_time)] += row["amount"]

    donation_product_rows = [row for row in product_rows if row.is_donation]
    total_product_donations = sum((row.amount for row in donation_product_rows), ZERO)
    total_remaining_credit_donations = Decimal(remaining_credit_donations or 0)
    total_cash_topups = sum((row.cash_topups for row in daily_cash.values()), ZERO)
    total_cash_sales = sum((row.cash_sales for row in daily_cash.values()), ZERO)
    total_cash_payouts = sum((row.cash_payouts for row in daily_cash.values()), ZERO)

    return AccountingReportContext(
        event_name=event_node.name,
        scope_name=scope_node.name,
        till_name=till_name,
        generated_at=datetime.now(tz=REPORT_TIMEZONE),
        from_time=_normalize_datetime(from_time).astimezone(REPORT_TIMEZONE),
        to_time=_normalize_datetime(to_time).astimezone(REPORT_TIMEZONE),
        includes_all_event_bookings=(
            not query.selected_dates and query.from_time is None and query.to_time is None
        ),
        daily_end_time=event.daily_end_time,
        selected_dates=query.selected_dates or [],
        currency_symbol=get_currency_symbol(event.currency_identifier),
        revenue_rows=revenue_rows,
        product_rows=product_rows,
        donation_product_rows=donation_product_rows,
        daily_cash_rows=[
            daily_cash[key] for key in sorted(daily_cash, key=lambda value: datetime.strptime(value, "%d.%m.%Y"))
        ],
        daily_online_topup_rows=[
            DailyOnlineTopUpRow(day=key, amount=daily_online[key])
            for key in sorted(daily_online, key=lambda value: datetime.strptime(value, "%d.%m.%Y"))
        ],
        total_revenue=sum((row.amount for row in revenue_rows), ZERO),
        total_cash_topups=total_cash_topups,
        total_cash_sales=total_cash_sales,
        total_cash_payouts=total_cash_payouts,
        total_cash_net=total_cash_topups + total_cash_sales - total_cash_payouts,
        total_online_topups=sum(daily_online.values(), ZERO),
        total_product_donations=total_product_donations,
        total_remaining_credit_donations=total_remaining_credit_donations,
        total_donations=total_product_donations + total_remaining_credit_donations,
        includes_remaining_credit_donations=includes_remaining_credit_donations,
    )


async def render_accounting_report(context: AccountingReportContext) -> PdfRenderResult:
    rendered = await render_template("accounting_report.tex", context, context.currency_symbol)
    return await pdflatex(file_content=rendered)


async def generate_accounting_report(conn: Connection, node: Node, query: AccountingReportQuery) -> PdfRenderResult:
    context = await build_accounting_report_context(conn=conn, node=node, query=query)
    return await render_accounting_report(context=context)
