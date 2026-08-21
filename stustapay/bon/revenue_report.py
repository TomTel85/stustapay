from datetime import date, datetime, time, timedelta, timezone

from pydantic import BaseModel
from sftkit.database import Connection

from stustapay.bon.bon import BonConfig, gen_dummy_order
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
from stustapay.core.schema.order import LineItem, Order
from stustapay.core.schema.tree import Node, RestrictedEventSettings
from stustapay.core.service.tree.common import fetch_event_for_node, fetch_node

GERMAN_WEEKDAYS = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
]


class DailyRevenue(BaseModel):
    day: str
    revenue: float
    fees: float
    revenue_minus_fees: float


class ReportSummary(BaseModel):
    order_count: int
    average_order_value: float
    average_day_revenue: float
    top_day_label: str
    top_day_revenue: float


class ReportLineItem(BaseModel):
    quantity: int
    product_name: str
    unit_price: float
    total_price: float


class ReportOrderEntry(BaseModel):
    time_label: str
    transaction_id: str
    customer_tag_uid_hex: str | None
    total_price: float
    line_items: list[ReportLineItem]


class ReportDayGroup(BaseModel):
    date_label: str
    day_total: float
    orders: list[ReportOrderEntry]


class RevenueReportQuery(BaseModel):
    selected_dates: list[str] | None = None
    day_mode: ReportDayMode = ReportDayMode.CALENDAR_DAY


class NodeReportContext(BaseModel):
    config: BonConfig
    orders: list[Order]
    daily_revenue_stats: list[DailyRevenue]
    summary: ReportSummary
    order_groups: list[ReportDayGroup]
    from_time: datetime
    to_time: datetime
    includes_all_event_bookings: bool
    selected_dates: list[str]
    day_mode: ReportDayMode
    daily_end_time: time | None
    node: Node

    total_revenue: float
    fees: float
    fees_percent: float
    revenue_minus_fees: float

    currency_symbol: str


class OrderWithFees(Order):
    fees: float
    total_price_minus_fees: float


async def render_report(context: NodeReportContext):
    rendered = await render_template("revenue_report.tex", context, context.currency_symbol)
    return await pdflatex(file_content=rendered)


async def generate_dummy_report(node_id: int, event: RestrictedEventSettings) -> PdfRenderResult:
    """Generate a dummy bon for the given event and return the pdf as bytes"""
    fee = 0.01

    dummy_orders = [gen_dummy_order(node_id)]
    orders = [
        OrderWithFees(
            fees=dummy_order.total_price * fee,
            total_price_minus_fees=dummy_order.total_price - dummy_order.total_price * fee,
            **dummy_order.model_dump(),
        )
        for dummy_order in dummy_orders
    ]
    daily_revenue = [
        DailyRevenue(
            day="Donnerstag 2024-10-10",
            revenue=10212,
            fees=10212 * fee,
            revenue_minus_fees=10212 - 10212 * fee,
        ),
        DailyRevenue(
            day="Freitag 2024-10-11",
            revenue=3000.23,
            fees=3000.23 * fee,
            revenue_minus_fees=3000.23 - 3000.23 * fee,
        ),
    ]
    ctx = _build_report_context(
        config=BonConfig(
            title=event.bon_title,
            issuer=event.bon_issuer,
            address=event.bon_address,
            ust_id=event.ust_id,
        ),
        node=Node(
            id=10,
            parent=5,
            name="Falafelstand",
            description="Fancy falafel",
            read_only=False,
            event=None,
            path="/0/5/10",
            parent_ids=[0, 5],
            event_node_id=5,
            parents_until_event_node=[5],
            forbidden_objects_at_node=[],
            computed_forbidden_objects_at_node=[],
            forbidden_objects_in_subtree=[],
            computed_forbidden_objects_in_subtree=[],
            children=[],
        ),
        orders=orders,
        daily_revenue=daily_revenue,
        from_time=datetime.now(tz=REPORT_TIMEZONE) - timedelta(days=3),
        to_time=datetime.now(tz=REPORT_TIMEZONE),
        total=sum(day.revenue for day in daily_revenue),
        fees=fee,
        currency_symbol=get_currency_symbol(event.currency_identifier),
        daily_end_time=event.daily_end_time,
        day_mode=ReportDayMode.EVENT_DAY if event.daily_end_time is not None else ReportDayMode.CALENDAR_DAY,
        selected_dates=[],
    )
    return await render_report(context=ctx)


def _check_order_revenue_consistency(daily_revenue: list[DailyRevenue], orders: list[OrderWithFees], total: float):
    stats_sum = sum(day.revenue for day in daily_revenue)
    orders_sum = sum([o.total_price for o in orders])
    if abs(orders_sum - stats_sum) > 1e-09:
        raise RuntimeError(
            f"Revenue statistics are not consistent between order list and aggregated stats. Order sum: {orders_sum}, stats sum: {stats_sum}"
        )

    if abs(stats_sum - total) > 1e-09:
        raise RuntimeError(
            f"Revenue statistics are not consistent between computed total and aggregated stats. Stats sum: {stats_sum}, total: {total}"
        )


def _to_report_timezone(dt: datetime) -> datetime:
    return normalize_datetime(dt).astimezone(REPORT_TIMEZONE)


def _format_day_label(value: date) -> str:
    return f"{GERMAN_WEEKDAYS[value.weekday()]} {value:%Y-%m-%d}"


def _build_report_line_items(line_items: list[LineItem]) -> list[ReportLineItem]:
    return [
        ReportLineItem(
            quantity=item.quantity,
            product_name=item.product.name,
            unit_price=item.product_price,
            total_price=item.total_price,
        )
        for item in line_items
    ]


def _build_order_groups(
    orders: list[OrderWithFees], daily_end_time: time | None, day_mode: ReportDayMode
) -> list[ReportDayGroup]:
    groups: dict[date, ReportDayGroup] = {}
    for order in orders:
        local_booked_at = _to_report_timezone(order.booked_at)
        day = report_day(order.booked_at, day_mode=day_mode, daily_end_time=daily_end_time)
        if day not in groups:
            groups[day] = ReportDayGroup(
                date_label=_format_day_label(day),
                day_total=0.0,
                orders=[],
            )

        groups[day].orders.append(
            ReportOrderEntry(
                time_label=local_booked_at.strftime("%H:%M"),
                transaction_id=f"{order.id:010}",
                customer_tag_uid_hex=order.customer_tag_uid_hex,
                total_price=order.total_price,
                line_items=_build_report_line_items(order.line_items),
            )
        )
        groups[day].day_total += order.total_price

    return [groups[day] for day in sorted(groups)]


def _build_summary(daily_revenue: list[DailyRevenue], orders: list[OrderWithFees], total: float) -> ReportSummary:
    order_count = len(orders)
    average_order_value = total / order_count if order_count else 0.0
    day_count = len(daily_revenue)
    average_day_revenue = total / day_count if day_count else 0.0
    top_day = max(daily_revenue, key=lambda day: day.revenue, default=None)

    return ReportSummary(
        order_count=order_count,
        average_order_value=average_order_value,
        average_day_revenue=average_day_revenue,
        top_day_label=top_day.day if top_day is not None else "Keine Umsaetze",
        top_day_revenue=top_day.revenue if top_day is not None else 0.0,
    )


def _build_daily_revenue(
    orders: list[OrderWithFees], *, fees: float, daily_end_time: time | None, day_mode: ReportDayMode
) -> tuple[list[DailyRevenue], float]:
    day_totals: dict[date, float] = {}
    for order in orders:
        day = report_day(order.booked_at, day_mode=day_mode, daily_end_time=daily_end_time)
        day_totals[day] = day_totals.get(day, 0.0) + order.total_price

    daily_revenue: list[DailyRevenue] = []
    total = 0.0
    for day in sorted(day_totals):
        revenue = day_totals[day]
        daily_fees = revenue * fees
        daily_revenue.append(
            DailyRevenue(
                day=_format_day_label(day),
                revenue=revenue,
                fees=daily_fees,
                revenue_minus_fees=revenue - daily_fees,
            )
        )
        total += revenue

    return daily_revenue, total


def _build_report_context(
    *,
    node: Node,
    orders: list[OrderWithFees],
    daily_revenue: list[DailyRevenue],
    from_time: datetime,
    to_time: datetime,
    total: float,
    fees: float,
    config: BonConfig,
    currency_symbol: str,
    daily_end_time: time | None,
    day_mode: ReportDayMode,
    selected_dates: list[str],
) -> NodeReportContext:
    fees_of_total = total * fees
    return NodeReportContext(
        node=node,
        orders=orders,
        currency_symbol=currency_symbol,
        config=config,
        daily_revenue_stats=daily_revenue,
        summary=_build_summary(daily_revenue=daily_revenue, orders=orders, total=total),
        order_groups=_build_order_groups(orders=orders, daily_end_time=daily_end_time, day_mode=day_mode),
        from_time=from_time,
        to_time=to_time,
        includes_all_event_bookings=not selected_dates,
        selected_dates=selected_dates,
        day_mode=day_mode,
        daily_end_time=daily_end_time,
        total_revenue=total,
        fees=fees_of_total,
        fees_percent=fees,
        revenue_minus_fees=total - fees_of_total,
    )


async def generate_report(
    conn: Connection, node_id: int, query: RevenueReportQuery | None = None, fees=0.0
) -> PdfRenderResult:
    query = query or RevenueReportQuery()
    node = await fetch_node(conn=conn, node_id=node_id)
    assert node is not None
    event = await fetch_event_for_node(conn=conn, node=node)
    assert node.event_node_id is not None
    event_node = await fetch_node(conn=conn, node_id=node.event_node_id)
    assert event_node is not None

    all_orders = await conn.fetch_many(
        OrderWithFees,
        "with scope_orders as materialized ("
        "   select o.id "
        "   from ordr o "
        "   join till t on o.till_id = t.id "
        "   join node n on n.id = t.node_id "
        "   where ($1 = any(n.parent_ids) or n.id = $1) "
        "     and o.payment_method = 'tag' "
        "     and o.order_type in ('sale', 'cancel_sale') "
        "     and not exists (select 1 from ordr c where c.cancels_order = o.id)"
        "), user_defined_line_item_json as materialized ("
        "   select "
        "       l.*, "
        "       row_to_json(p) as product "
        "   from line_item l "
        "   join product_with_tax_and_restrictions p on l.product_id = p.id "
        "   join scope_orders so on so.id = l.order_id "
        "   where p.type = 'user_defined'"
        "), user_defined_line_items as materialized ("
        "   select "
        "       order_id, "
        "       sum(total_price) as total_price, "
        "       sum(total_tax) as total_tax, "
        "       sum(total_price - total_tax) as total_no_tax, "
        "       coalesce(json_agg(user_defined_line_item_json), json_build_array()) as line_items "
        "   from user_defined_line_item_json "
        "   group by order_id"
        ") "
        "select "
        "   o.*, "
        "   ut.uid as customer_tag_uid, "
        "   ut.id as customer_tag_id, "
        "   li.total_price, "
        "   li.total_tax, "
        "   li.total_no_tax, "
        "   li.line_items, "
        "   li.total_price * $2 as fees, "
        "   li.total_price - li.total_price * $2 as total_price_minus_fees "
        "from ordr o "
        "join scope_orders so on so.id = o.id "
        "join user_defined_line_items li on li.order_id = o.id "
        "left join account a on o.customer_account_id = a.id "
        "left join user_tag ut on a.user_tag_id = ut.id "
        "order by o.booked_at",
        node_id,
        fees,
    )
    selected_ranges = selected_date_ranges(
        query.selected_dates,
        day_mode=query.day_mode,
        daily_end_time=event.daily_end_time,
    )
    orders = [order for order in all_orders if is_in_ranges(order.booked_at, selected_ranges)]
    if selected_ranges:
        from_time = selected_ranges[0][0]
        to_time = selected_ranges[-1][1]
    elif orders:
        from_time = normalize_datetime(orders[0].booked_at)
        to_time = normalize_datetime(orders[-1].booked_at)
    else:
        fallback = event.start_date or event.end_date or datetime.now(tz=timezone.utc)
        from_time = normalize_datetime(fallback)
        to_time = from_time
    from_time_local = from_time.astimezone(REPORT_TIMEZONE)
    to_time_local = to_time.astimezone(REPORT_TIMEZONE)

    config = BonConfig(ust_id=event.ust_id, address=event.bon_address, issuer=event.bon_issuer, title=event_node.name)
    daily_revenue, total = _build_daily_revenue(
        orders,
        fees=fees,
        daily_end_time=event.daily_end_time,
        day_mode=query.day_mode,
    )
    _check_order_revenue_consistency(daily_revenue, orders, total)

    context = _build_report_context(
        node=node,
        orders=orders,
        from_time=from_time_local,
        to_time=to_time_local,
        total=total,
        fees=fees,
        config=config,
        currency_symbol=get_currency_symbol(event.currency_identifier),
        daily_revenue=daily_revenue,
        daily_end_time=event.daily_end_time,
        day_mode=query.day_mode,
        selected_dates=query.selected_dates or [],
    )
    return await render_report(context=context)
