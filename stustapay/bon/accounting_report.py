from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, Field
from sftkit.database import Connection
from sftkit.error import InvalidArgument

from stustapay.bon.pdflatex import PdfRenderResult, pdflatex, render_template
from stustapay.bon.report_time import (
    REPORT_TIMEZONE,
    ReportDayMode,
    is_in_ranges,
    normalize_datetime,
    report_day,
    selected_date_ranges,
)
from stustapay.core.currency import get_currency_symbol
from stustapay.core.schema.tree import Node, PublicEventSettings
from stustapay.core.service.order.stats import TimeseriesStatsQuery, get_event_time_bounds
from stustapay.core.service.tree.common import fetch_event_for_node, fetch_node

ZERO = Decimal("0")


class AccountingReportQuery(BaseModel):
    from_time: datetime | None = None
    to_time: datetime | None = None
    till_id: int | None = None
    subnode_id: int | None = None
    selected_dates: list[str] | None = None
    day_mode: ReportDayMode = ReportDayMode.CALENDAR_DAY


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


class MonthlyDepositProductRow(BaseModel):
    product_id: int
    product_name: str
    received: Decimal = ZERO
    refunded: Decimal = ZERO

    @property
    def net(self) -> Decimal:
        return self.received - self.refunded


class MonthlyAccountingRow(BaseModel):
    month: str
    provisional: bool
    deposit_received: Decimal = ZERO
    deposit_refunded: Decimal = ZERO
    deposit_products: list[MonthlyDepositProductRow] = Field(default_factory=list)
    donation_products_received: Decimal = ZERO
    donation_products_refunded: Decimal = ZERO
    remaining_credit_donations_received: Decimal = ZERO
    remaining_credit_donations_refunded: Decimal = ZERO
    remaining_credit: Decimal = ZERO

    @property
    def donations_received(self) -> Decimal:
        return self.donation_products_received + self.remaining_credit_donations_received

    @property
    def donations_refunded(self) -> Decimal:
        return self.donation_products_refunded + self.remaining_credit_donations_refunded

    @property
    def donations_net(self) -> Decimal:
        return self.donations_received - self.donations_refunded


class AccountingReportContext(BaseModel):
    event_name: str
    scope_name: str
    till_name: str | None
    generated_at: datetime
    from_time: datetime
    to_time: datetime
    includes_all_event_bookings: bool
    daily_end_time: time | None
    day_mode: ReportDayMode
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
    monthly_rows: list[MonthlyAccountingRow]


def _resolve_bounds(query: AccountingReportQuery, event: PublicEventSettings) -> tuple[datetime, datetime]:
    ranges = selected_date_ranges(
        query.selected_dates,
        day_mode=query.day_mode,
        daily_end_time=event.daily_end_time,
    )
    if ranges:
        return ranges[0][0], ranges[-1][1]
    stats_query = TimeseriesStatsQuery(
        from_time=query.from_time,
        to_time=query.to_time,
        till_id=query.till_id,
        subnode_id=query.subnode_id,
        selected_dates=None,
    )
    return get_event_time_bounds(stats_query, event)


def _report_day(value: datetime, daily_end_time: time | None, day_mode: ReportDayMode) -> str:
    return report_day(value, day_mode=day_mode, daily_end_time=daily_end_time).strftime("%d.%m.%Y")


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


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _next_month(value: date) -> date:
    return date(value.year + (value.month == 12), value.month % 12 + 1, 1)


def _selected_months(selected_dates: list[str] | None) -> set[date]:
    months: set[date] = set()
    for entry in selected_dates or []:
        for part in entry.split(","):
            if part.strip():
                months.add(_month_start(date.fromisoformat(part.strip())))
    return months


async def _build_monthly_rows(
    conn: Connection, event_node_id: int, selected_dates: list[str] | None, generated_at: datetime
) -> list[MonthlyAccountingRow]:
    # Product reversals are separate orders. Use their own booking date instead of
    # retroactively removing the original sale from a closed month.
    product_movements = await conn.fetch(
        "select date_trunc('month', o.booked_at at time zone 'Europe/Berlin')::date as booking_day, "
        "p.id as product_id, p.name as product_name, p.is_returnable, p.is_donation, "
        "sum(li.total_price) as amount "
        "from ordr o join till t on t.id = o.till_id join node n on n.id = t.node_id "
        "join line_item li on li.order_id = o.id join product p on p.id = li.product_id "
        "where n.event_node_id = $1 and o.order_type in ('sale', 'cancel_sale') "
        "and (p.is_returnable or p.is_donation) and o.booked_at <= $2 "
        "group by booking_day, p.id, p.name, p.is_returnable, p.is_donation, (li.total_price >= 0)",
        event_node_id,
        generated_at,
    )
    donation_movements = await conn.fetch(
        "select date_trunc('month', tr.booked_at at time zone 'Europe/Berlin')::date as booking_day, "
        "sum(case when sa.type = 'private' then tr.amount else -tr.amount end) as amount "
        "from transaction tr join account sa on sa.id = tr.source_account "
        "join account ta on ta.id = tr.target_account "
        "join node sn on sn.id = sa.node_id join node tn on tn.id = ta.node_id "
        "where tr.booked_at <= $2 and ((sa.type = 'private' and ta.type = 'donation_exit' "
        "and sn.event_node_id = $1 and tn.event_node_id = $1) "
        "or (sa.type = 'donation_exit' and ta.type = 'private' "
        "and sn.event_node_id = $1 and tn.event_node_id = $1)) "
        "group by booking_day, sa.type",
        event_node_id,
        generated_at,
    )
    # Accounts start at zero, and book_transaction records every balance change.
    # Include both sides so transfers between private accounts net to zero.
    account_movements = await conn.fetch(
        "select a.id as account_id, date_trunc('month', tr.booked_at at time zone 'Europe/Berlin')::date "
        "as booking_day, sum(case when tr.target_account = a.id and tr.source_account = a.id then 0 "
        "when tr.target_account = a.id then tr.amount else -tr.amount end) as amount "
        "from account a join node n on n.id = a.node_id "
        "join transaction tr on tr.source_account = a.id or tr.target_account = a.id "
        "where a.type = 'private' and n.event_node_id = $1 and tr.booked_at <= $2 "
        "group by a.id, booking_day order by booking_day, a.id",
        event_node_id,
        generated_at,
    )

    months = _selected_months(selected_dates)
    if not selected_dates:
        months.update(_month_start(row["booking_day"]) for row in product_movements)
        months.update(_month_start(row["booking_day"]) for row in donation_movements)
        months.update(_month_start(row["booking_day"]) for row in account_movements)
    rows = {
        month: MonthlyAccountingRow(
            month=month.strftime("%m.%Y"), provisional=month == _month_start(generated_at.date())
        )
        for month in sorted(months)
        if month <= _month_start(generated_at.date())
    }
    deposit_products: dict[tuple[date, int], MonthlyDepositProductRow] = {}
    for movement in product_movements:
        month = _month_start(movement["booking_day"])
        row = rows.get(month)
        if row is None:
            continue
        amount = movement["amount"]
        if movement["is_returnable"]:
            product_key = (month, movement["product_id"])
            product_row = deposit_products.setdefault(
                product_key,
                MonthlyDepositProductRow(product_id=movement["product_id"], product_name=movement["product_name"]),
            )
            if amount >= 0:
                row.deposit_received += amount
                product_row.received += amount
            else:
                row.deposit_refunded -= amount
                product_row.refunded -= amount
        if movement["is_donation"]:
            if amount >= 0:
                row.donation_products_received += amount
            else:
                row.donation_products_refunded -= amount
    for (month, _product_id), product_row in deposit_products.items():
        rows[month].deposit_products.append(product_row)
    for row in rows.values():
        row.deposit_products.sort(key=lambda product: (product.product_name.casefold(), product.product_id))
    for movement in donation_movements:
        row = rows.get(_month_start(movement["booking_day"]))
        if row is not None:
            amount = movement["amount"]
            if amount >= 0:
                row.remaining_credit_donations_received += amount
            else:
                row.remaining_credit_donations_refunded -= amount

    account_balances: dict[int, Decimal] = defaultdict(lambda: ZERO)
    movements = iter(account_movements)
    movement = next(movements, None)
    for month in sorted(rows):
        while movement is not None and movement["booking_day"] < _next_month(month):
            account_balances[movement["account_id"]] += movement["amount"]
            movement = next(movements, None)
        rows[month].remaining_credit = sum((balance for balance in account_balances.values() if balance > 0), ZERO)
    return list(rows.values())


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
    generated_at = datetime.now(tz=REPORT_TIMEZONE)
    monthly_rows = await _build_monthly_rows(
        conn=conn, event_node_id=node.event_node_id, selected_dates=query.selected_dates, generated_at=generated_at
    )
    selected_ranges = selected_date_ranges(
        query.selected_dates,
        day_mode=query.day_mode,
        daily_end_time=event.daily_end_time,
    )

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
        remaining_credit_rows = await conn.fetch(
            "select tr.booked_at, tr.amount "
            "from transaction tr "
            "join account sa on sa.id = tr.source_account "
            "join account ta on ta.id = tr.target_account "
            "where sa.type = 'private' and ta.type = 'donation_exit' and ta.node_id = $1 "
            "and tr.booked_at >= $2 and tr.booked_at <= $3",
            node.event_node_id,
            from_time,
            to_time,
        )
        remaining_credit_donations = sum(
            (row["amount"] for row in remaining_credit_rows if is_in_ranges(row["booked_at"], selected_ranges)),
            ZERO,
        )

    product_aggregation: dict[tuple[str, str, str, str, bool], tuple[int, Decimal]] = {}
    revenue_aggregation: dict[tuple[str, str, str], Decimal] = defaultdict(lambda: ZERO)
    for row in sales_rows:
        if not is_in_ranges(row["booked_at"], selected_ranges):
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
        if not is_in_ranges(row["booked_at"], selected_ranges):
            continue
        day = _report_day(row["booked_at"], event.daily_end_time, query.day_mode)
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
        if is_in_ranges(row["booked_at"], selected_ranges):
            daily_online[_report_day(row["booked_at"], event.daily_end_time, query.day_mode)] += row["amount"]

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
        generated_at=generated_at,
        from_time=normalize_datetime(from_time).astimezone(REPORT_TIMEZONE),
        to_time=normalize_datetime(to_time).astimezone(REPORT_TIMEZONE),
        includes_all_event_bookings=(not query.selected_dates and query.from_time is None and query.to_time is None),
        daily_end_time=event.daily_end_time,
        day_mode=query.day_mode,
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
        monthly_rows=monthly_rows,
    )


async def render_accounting_report(context: AccountingReportContext) -> PdfRenderResult:
    rendered = await render_template("accounting_report.tex", context, context.currency_symbol)
    return await pdflatex(file_content=rendered)


async def generate_accounting_report(conn: Connection, node: Node, query: AccountingReportQuery) -> PdfRenderResult:
    context = await build_accounting_report_context(conn=conn, node=node, query=query)
    return await render_accounting_report(context=context)
