from typing import Optional

from stustapay.core.schema.till import NewTill, Till
from stustapay.core.schema.tree import Node
from stustapay.framework.database import Connection


async def create_till(*, conn: Connection, node_id: int, till: NewTill) -> Till:
    return await conn.fetch_one(
        Till,
        "insert into till "
        "   (name, description, active_shift, active_profile_id, node_id, terminal_id) "
        "values ($1, $2, $3, $4, $5, $6) returning id, name, description, "
        "   tse_id, active_shift, active_profile_id, z_nr, node_id, terminal_id",
        till.name,
        till.description,
        till.active_shift,
        till.active_profile_id,
        till.active_tse_id,
        node_id,
        till.terminal_id,
    )


async def fetch_till(*, conn: Connection, node: Node, till_id: int) -> Optional[Till]:
    return await conn.fetch_maybe_one(
        Till,
        "select * from till where id = $1 and node_id = any($2)",
        till_id,
        node.ids_to_event_node,
    )


async def fetch_virtual_till(*, conn: Connection, node: Node) -> Till:
    return await conn.fetch_one(
        Till, "select * from till where is_virtual and node_id = any($1)", node.ids_to_event_node
    )
