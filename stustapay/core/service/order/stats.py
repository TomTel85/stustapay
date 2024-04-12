from datetime import datetime
from typing import Optional

import asyncpg
from pydantic import BaseModel

from stustapay.core.config import Config
from stustapay.core.schema.product import Product
from stustapay.core.schema.tree import Node, PublicEventSettings
from stustapay.core.schema.user import Privilege
from stustapay.core.service.auth import AuthService
from stustapay.core.service.common.dbservice import DBService
from stustapay.core.service.common.decorators import (
    requires_node,
    requires_user,
    with_db_transaction,
)
from stustapay.core.service.common.error import InvalidArgument
from stustapay.core.service.product import fetch_top_up_product
from stustapay.core.service.tree.common import fetch_event_for_node
from stustapay.framework.database import Connection


class ProductSoldStats(Product):
    quantity_sold: int


class VoucherStats(BaseModel):
    vouchers_issued: int
    vouchers_spent: int


class OverviewStats(BaseModel):
    n_transactions: int


class StatInterval(BaseModel):
    from_time: datetime
    to_time: datetime
    count: int
    revenue: float


class Timeseries(BaseModel):
    from_time: datetime
    to_time: datetime
    intervals: list[StatInterval]


class TimeseriesStats(BaseModel):
    from_time: datetime
    to_time: datetime
    daily_intervals: list[StatInterval]
    hourly_intervals: list[StatInterval]


class TimeseriesStatsQuery(BaseModel):
    from_time: Optional[datetime]
    to_time: Optional[datetime]


class ProductTimeseries(BaseModel):
    product_id: int
    intervals: list[StatInterval]


class ProductStats(BaseModel):
    from_time: datetime
    to_time: datetime
    daily_intervals: list[StatInterval]
    hourly_intervals: list[StatInterval]
    product_daily_intervals: list[ProductTimeseries]
    product_hourly_intervals: list[ProductTimeseries]


def _get_time_bounds(query: TimeseriesStatsQuery, event: PublicEventSettings) -> tuple[datetime, datetime]:
    if query.from_time is not None and query.to_time is not None and query.from_time > query.to_time:
        raise InvalidArgument("Stats start time must be before end time")

    from_t = query.from_time or event.start_date or datetime(year=1970, month=1, day=1)
    to_t = query.to_time or event.end_date or datetime(year=4000, month=1, day=1)
    return from_t, to_t


async def get_hourly_entry_stats(*, conn: Connection, node: Node, from_time: datetime, to_time: datetime) -> Timeseries:
    stats = await conn.fetch_many(
        StatInterval,
        "select "
        "   date_trunc('hour', o.booked_at) as from_time, "
        "   date_trunc('hour', o.booked_at) + interval '1 hour' as to_time, "
        "   sum(li.quantity) as count,"
        "   round(sum(li.total_price), 2) as revenue "
        "from order_value o "
        "join till t on o.till_id = t.id "
        "join line_item li on o.id = li.order_id "
        "join product p on li.product_id = p.id "
        "join node n on t.node_id = n.id "
        "where p.ticket_metadata_id is not null and o.booked_at >= $1 and o.booked_at <= $2 "
        "   and ($3 = any(n.parent_ids) or n.id = $3) "
        "group by from_time, to_time "
        "order by from_time",
        from_time,
        to_time,
        node.id,
    )

    return Timeseries(from_time=from_time, to_time=to_time, intervals=stats)


async def get_hourly_top_up_stats(
    *, conn: Connection, node: Node, from_time: datetime, to_time: datetime
) -> Timeseries:
    top_up_product = await fetch_top_up_product(conn=conn, node=node)

    stats = await conn.fetch_many(
        StatInterval,
        "select "
        "   date_trunc('hour', o.booked_at) as from_time, "
        "   date_trunc('hour', o.booked_at) + interval '1 hour' as to_time, "
        "   sum(li.quantity) as count,"
        "   round(sum(li.total_price), 2) as revenue "
        "from order_value o "
        "join till t on o.till_id = t.id "
        "join line_item li on o.id = li.order_id "
        "join product p on li.product_id = p.id "
        "join node n on t.node_id = n.id "
        "where p.id = $4 and o.booked_at >= $1 and o.booked_at <= $2 "
        "   and ($3 = any(n.parent_ids) or n.id = $3) "
        "group by from_time, to_time "
        "order by from_time",
        from_time,
        to_time,
        node.id,
        top_up_product.id,
    )

    return Timeseries(from_time=from_time, to_time=to_time, intervals=stats)


async def get_hourly_revenue_stats(
    *, conn: Connection, node: Node, from_time: datetime, to_time: datetime
) -> Timeseries:

    stats = await conn.fetch_many(
        StatInterval,
        "select "
        "   date_trunc('hour', o.booked_at) as from_time, "
        "   date_trunc('hour', o.booked_at) + interval '1 hour' as to_time, "
        "   sum(li.quantity) as count,"
        "   round(sum(li.total_price), 2) as revenue "
        "from order_value o "
        "join till t on o.till_id = t.id "
        "join line_item li on o.id = li.order_id "
        "join product p on li.product_id = p.id "
        "join node n on t.node_id = n.id "
        "where o.booked_at >= $1 and o.booked_at <= $2 "
        "   and p.type = 'user_defined' "
        "   and ($3 = any(n.parent_ids) or n.id = $3) "
        "group by from_time, to_time "
        "order by from_time",
        from_time,
        to_time,
        node.id,
    )

    return Timeseries(from_time=from_time, to_time=to_time, intervals=stats)


async def get_hourly_product_stats(
    *, conn: Connection, node: Node, from_time: datetime, to_time: datetime
) -> list[ProductTimeseries]:
    result = await conn.fetch(
        "select "
        "   p.id as product_id, "
        "   date_trunc('hour', o.booked_at) as from_time, "
        "   date_trunc('hour', o.booked_at) + interval '1 hour' as to_time, "
        "   sum(li.quantity) as count,"
        "   round(sum(li.total_price), 2) as revenue "
        "from order_value o "
        "join till t on o.till_id = t.id "
        "join line_item li on o.id = li.order_id "
        "join product p on li.product_id = p.id "
        "join node n on t.node_id = n.id "
        "where o.booked_at >= $1 and o.booked_at <= $2 "
        "   and p.type = 'user_defined' "
        "   and ($3 = any(n.parent_ids) or n.id = $3) "
        "   and not p.is_returnable "
        "group by p.id, from_time, to_time "
        "order by from_time",
        from_time,
        to_time,
        node.id,
    )
    product_timeseries_map: dict[int, list[StatInterval]] = {}
    for row in result:
        product_timeseries_map.setdefault(row["product_id"], []).append(
            StatInterval(from_time=row["from_time"], to_time=row["to_time"], count=row["count"], revenue=row["revenue"])
        )
    return [
        ProductTimeseries(product_id=p_id, intervals=intervals) for p_id, intervals in product_timeseries_map.items()
    ]


async def get_daily_stats(*, hourly_stats: Timeseries, event: PublicEventSettings) -> Timeseries:
    if event.daily_end_time is None:
        raise InvalidArgument("daily end time must be set for this event to accurately compute the daily statistics")
    if event.start_date is None or event.end_date is None:
        raise InvalidArgument(
            "event start and end dates must be set for this event to accurately compute the daily statistics"
        )

    next_day = hourly_stats.from_time.replace(
        day=hourly_stats.from_time.day + 1,
        hour=event.daily_end_time.hour,
        minute=event.daily_end_time.minute,
        second=event.daily_end_time.second,
    )
    stats = []
    current_interval = StatInterval(
        from_time=hourly_stats.from_time,
        to_time=next_day,
        count=0,
        revenue=0,
    )
    for hourly_stat in hourly_stats.intervals:
        if hourly_stat.from_time > next_day:
            stats.append(current_interval)
            current_interval = StatInterval(
                from_time=next_day,
                to_time=next_day.replace(day=next_day.day + 1),
                count=0,
                revenue=0,
            )
            next_day = next_day.replace(day=next_day.day + 1)
        current_interval.count += hourly_stat.count  # pylint: disable=no-member
        current_interval.revenue += hourly_stat.revenue  # pylint: disable=no-member
    stats.append(current_interval)
    return Timeseries(from_time=hourly_stats.from_time, to_time=hourly_stats.to_time, intervals=stats)


class OrderStatsService(DBService):
    def __init__(self, db_pool: asyncpg.Pool, config: Config, auth_service: AuthService):
        super().__init__(db_pool, config)
        self.auth_service = auth_service

    @with_db_transaction(read_only=True)
    @requires_node(event_only=True)
    @requires_user([Privilege.node_administration])
    async def get_entry_stats(self, *, conn: Connection, node: Node, query: TimeseriesStatsQuery) -> TimeseriesStats:
        if node.event is None:
            raise InvalidArgument("Entry stats can only be computed for event nodes")

        event = await fetch_event_for_node(conn=conn, node=node)
        from_time, to_time = _get_time_bounds(query, event)

        hourly_stats = await get_hourly_entry_stats(conn=conn, node=node, from_time=from_time, to_time=to_time)
        daily_stats = await get_daily_stats(hourly_stats=hourly_stats, event=event)
        return TimeseriesStats(
            from_time=hourly_stats.from_time,
            to_time=hourly_stats.to_time,
            hourly_intervals=hourly_stats.intervals,
            daily_intervals=daily_stats.intervals,
        )

    @with_db_transaction(read_only=True)
    @requires_node(event_only=True)
    @requires_user([Privilege.node_administration])
    async def get_top_up_stats(self, *, conn: Connection, node: Node, query: TimeseriesStatsQuery) -> TimeseriesStats:
        if node.event is None:
            raise InvalidArgument("Top up stats can only be computed for event nodes")

        event = await fetch_event_for_node(conn=conn, node=node)
        from_time, to_time = _get_time_bounds(query, event)

        hourly_stats = await get_hourly_top_up_stats(conn=conn, node=node, from_time=from_time, to_time=to_time)
        daily_stats = await get_daily_stats(hourly_stats=hourly_stats, event=event)
        return TimeseriesStats(
            from_time=hourly_stats.from_time,
            to_time=hourly_stats.to_time,
            hourly_intervals=hourly_stats.intervals,
            daily_intervals=daily_stats.intervals,
        )

    @with_db_transaction(read_only=True)
    @requires_node(event_only=True)
    @requires_user([Privilege.node_administration])
    async def get_voucher_stats(self, *, conn: Connection, node: Node, query: TimeseriesStatsQuery) -> VoucherStats:
        if node.event is None:
            raise InvalidArgument("voucher stats can only be computed for event nodes")

        event = await fetch_event_for_node(conn=conn, node=node)
        from_time, to_time = _get_time_bounds(query, event)

        stats = await conn.fetch_one(
            VoucherStats,
            "select "
            "   coalesce(sum(case when sa.type = 'voucher_create' then t.vouchers else 0 end), 0) as vouchers_issued, "
            "   coalesce(sum(case when sa.type != 'voucher_create' then t.vouchers else 0 end), 0) as vouchers_spent "
            "from transaction t "
            "join account sa on t.source_account = sa.id "
            "join account ta on t.target_account = ta.id "
            "where t.booked_at >= $1 and t.booked_at <= $2"
            "   and sa.node_id = $3",
            from_time,
            to_time,
            node.event_node_id,
        )

        return stats

    @with_db_transaction(read_only=True)
    @requires_node(event_only=True)
    @requires_user([Privilege.node_administration])
    async def get_product_stats(self, *, conn: Connection, node: Node, query: TimeseriesStatsQuery) -> ProductStats:
        event = await fetch_event_for_node(conn=conn, node=node)
        from_time, to_time = _get_time_bounds(query, event)
        hourly_stats = await get_hourly_revenue_stats(conn=conn, node=node, from_time=from_time, to_time=to_time)
        daily_stats = await get_daily_stats(hourly_stats=hourly_stats, event=event)

        hourly_product_stats = await get_hourly_product_stats(
            conn=conn, node=node, from_time=from_time, to_time=to_time
        )
        daily_product_stats = {}
        for hourly_product in hourly_product_stats:
            d = await get_daily_stats(
                hourly_stats=Timeseries(from_time=from_time, to_time=to_time, intervals=hourly_product.intervals),
                event=event,
            )
            daily_product_stats[hourly_product.product_id] = d.intervals

        return ProductStats(
            from_time=hourly_stats.from_time,
            to_time=hourly_stats.to_time,
            hourly_intervals=hourly_stats.intervals,
            daily_intervals=daily_stats.intervals,
            product_hourly_intervals=hourly_product_stats,
            product_daily_intervals=[
                ProductTimeseries(product_id=p_id, intervals=intervals)
                for p_id, intervals in daily_product_stats.items()
            ],
        )
