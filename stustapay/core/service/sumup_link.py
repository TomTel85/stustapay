from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel
from sftkit.database import Connection
from sftkit.error import InvalidArgument

from stustapay.core.schema.sumup import (
    NodeSumUpConnectionStatus,
    ResolvedSumUpLink,
    SumUpAuthMethod,
    SumUpConnectionSource,
    SumUpEnvironment,
)
from stustapay.core.schema.tree import Node, RestrictedEventSettings
from stustapay.core.service.config import fetch_global_sumup_config
from stustapay.core.service.tree.common import (
    fetch_event_node_for_node,
    fetch_node,
    fetch_restricted_event_settings_for_node,
)
from stustapay.payment.sumup.api import SumUpApi, fetch_new_oauth_token


class NodeSumUpLinkRecord(BaseModel):
    node_id: int
    node_name: str
    environment: SumUpEnvironment
    auth_method: SumUpAuthMethod
    merchant_code: str
    merchant_name: str | None = None
    refresh_token: str | None = None
    api_key: str | None = None


@dataclass
class ResolvedSumUpAccess:
    source: SumUpConnectionSource
    environment: SumUpEnvironment
    auth_method: SumUpAuthMethod
    source_node_id: int
    source_node_name: str
    merchant_code: str
    merchant_name: str | None = None
    api_key: str | None = None
    refresh_token: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    affiliate_key: str = ""

    @property
    def is_oauth(self) -> bool:
        return (
            self.refresh_token is not None and self.oauth_client_id is not None and self.oauth_client_secret is not None
        )


async def fetch_direct_node_sumup_link(
    conn: Connection, node_id: int, environment: SumUpEnvironment
) -> NodeSumUpLinkRecord | None:
    return await conn.fetch_maybe_one(
        NodeSumUpLinkRecord,
        "select l.node_id, n.name as node_name, l.environment, l.auth_method, "
        "l.merchant_code, l.merchant_name, l.refresh_token, l.api_key "
        "from node_sumup_link l "
        "join node n on n.id = l.node_id "
        "where l.node_id = $1 and l.environment = $2",
        node_id,
        environment.value,
    )


async def fetch_nearest_node_sumup_link_for_event(
    conn: Connection, event_node: Node, environment: SumUpEnvironment
) -> NodeSumUpLinkRecord | None:
    if len(event_node.parent_ids) == 0:
        return None
    return await conn.fetch_maybe_one(
        NodeSumUpLinkRecord,
        "with candidate_nodes(node_id, ord) as ("
        "    select * from unnest($1::bigint[]) with ordinality"
        ") "
        "select l.node_id, n.name as node_name, l.environment, l.auth_method, "
        "l.merchant_code, l.merchant_name, l.refresh_token, l.api_key "
        "from candidate_nodes c "
        "join node_sumup_link l on l.node_id = c.node_id "
        "join node n on n.id = l.node_id "
        "where l.environment = $2 "
        "order by c.ord desc "
        "limit 1",
        event_node.parent_ids,
        environment.value,
    )


async def count_linked_events_for_node(conn: Connection, node_id: int, environment: SumUpEnvironment) -> int:
    return await conn.fetchval(
        "select count(*) from node n "
        "join event e on e.id = n.event_id "
        "where n.event_id is not null and $1 = any(n.parent_ids) and e.sumup_environment = $2",
        node_id,
        environment.value,
    )


async def count_pending_orders_for_node(conn: Connection, node_id: int, environment: SumUpEnvironment) -> int:
    return await conn.fetchval(
        "select count(*) from pending_sumup_order pso "
        "join node n on n.id = pso.node_id "
        "where pso.status = 'pending' and pso.sumup_environment = $1 and $2 = any(n.parent_ids)",
        environment.value,
        node_id,
    )


async def ensure_sumup_link_can_be_replaced(
    conn: Connection,
    *,
    node_id: int,
    environment: SumUpEnvironment,
    merchant_code: str,
) -> None:
    current_link = await fetch_direct_node_sumup_link(conn=conn, node_id=node_id, environment=environment)
    if current_link is None or current_link.merchant_code == merchant_code:
        return
    if await count_pending_orders_for_node(conn=conn, node_id=node_id, environment=environment):
        raise InvalidArgument(f"Cannot replace the {environment.value} SumUp merchant while payments are pending")


async def get_node_sumup_connection_status(
    conn: Connection, node: Node, environment: SumUpEnvironment = SumUpEnvironment.live
) -> NodeSumUpConnectionStatus:
    global_sumup = await fetch_global_sumup_config(conn=conn)
    direct_link = await fetch_direct_node_sumup_link(conn=conn, node_id=node.id, environment=environment)
    linked_event_count = await count_linked_events_for_node(conn=conn, node_id=node.id, environment=environment)
    return NodeSumUpConnectionStatus(
        node_id=node.id,
        node_name=node.name,
        environment=environment,
        auth_method=direct_link.auth_method if direct_link is not None else None,
        connected=direct_link is not None,
        merchant_code=direct_link.merchant_code if direct_link is not None else None,
        merchant_name=direct_link.merchant_name if direct_link is not None else None,
        linked_event_count=linked_event_count,
        oauth_client_id=global_sumup.sumup_oauth_client_id,
        oauth_configured=bool(
            global_sumup.sumup_oauth_client_id.strip() and global_sumup.sumup_oauth_client_secret.strip()
        ),
        affiliate_key_configured=bool(global_sumup.sumup_affiliate_key.strip()),
    )


async def upsert_node_sumup_oauth_link(
    conn: Connection,
    *,
    node: Node,
    merchant_code: str,
    merchant_name: str | None,
    refresh_token: str,
) -> NodeSumUpConnectionStatus:
    if node.event is not None or node.event_node_id is not None:
        raise InvalidArgument("SumUp merchant links can only be configured on nodes above events")
    await ensure_sumup_link_can_be_replaced(
        conn=conn,
        node_id=node.id,
        environment=SumUpEnvironment.live,
        merchant_code=merchant_code,
    )
    await conn.execute(
        "insert into node_sumup_link "
        "(node_id, environment, auth_method, merchant_code, merchant_name, refresh_token, api_key, connected_at, updated_at) "
        "values ($1, 'live', 'oauth', $2, $3, $4, null, now(), now()) "
        "on conflict (node_id, environment) do update set "
        "auth_method = excluded.auth_method, "
        "merchant_code = excluded.merchant_code, "
        "merchant_name = excluded.merchant_name, "
        "refresh_token = excluded.refresh_token, "
        "api_key = null, "
        "updated_at = now()",
        node.id,
        merchant_code,
        merchant_name,
        refresh_token,
    )
    return await get_node_sumup_connection_status(conn=conn, node=node, environment=SumUpEnvironment.live)


async def upsert_node_sumup_api_key_link(
    conn: Connection,
    *,
    node: Node,
    environment: SumUpEnvironment,
    merchant_code: str,
    merchant_name: str | None,
    api_key: str,
) -> NodeSumUpConnectionStatus:
    if node.event is not None or node.event_node_id is not None:
        raise InvalidArgument("SumUp merchant links can only be configured on nodes above events")
    await ensure_sumup_link_can_be_replaced(
        conn=conn,
        node_id=node.id,
        environment=environment,
        merchant_code=merchant_code,
    )
    await conn.execute(
        "insert into node_sumup_link "
        "(node_id, environment, auth_method, merchant_code, merchant_name, refresh_token, api_key, connected_at, updated_at) "
        "values ($1, $2, 'api_key', $3, $4, null, $5, now(), now()) "
        "on conflict (node_id, environment) do update set "
        "auth_method = excluded.auth_method, "
        "merchant_code = excluded.merchant_code, "
        "merchant_name = excluded.merchant_name, "
        "refresh_token = null, "
        "api_key = excluded.api_key, "
        "updated_at = now()",
        node.id,
        environment.value,
        merchant_code,
        merchant_name,
        api_key,
    )
    return await get_node_sumup_connection_status(conn=conn, node=node, environment=environment)


async def delete_node_sumup_link(
    conn: Connection, *, node: Node, environment: SumUpEnvironment = SumUpEnvironment.live
) -> NodeSumUpConnectionStatus:
    if node.event is not None or node.event_node_id is not None:
        raise InvalidArgument("SumUp merchant links can only be configured on nodes above events")
    pending_order_count = await count_pending_orders_for_node(conn=conn, node_id=node.id, environment=environment)
    if pending_order_count:
        raise InvalidArgument(f"Cannot disconnect the {environment.value} SumUp merchant while payments are pending")
    await conn.execute(
        "delete from node_sumup_link where node_id = $1 and environment = $2",
        node.id,
        environment.value,
    )
    return await get_node_sumup_connection_status(conn=conn, node=node, environment=environment)


async def resolve_sumup_access(
    conn: Connection,
    node_id: int,
    environment: SumUpEnvironment | None = None,
    event_settings: RestrictedEventSettings | None = None,
) -> ResolvedSumUpAccess | None:
    event_node = await fetch_event_node_for_node(conn=conn, node_id=node_id)
    assert event_node is not None
    resolved_event_settings = event_settings or await fetch_restricted_event_settings_for_node(
        conn=conn, node_id=node_id
    )
    resolved_environment = environment or resolved_event_settings.sumup_environment
    global_sumup = await fetch_global_sumup_config(conn=conn)
    affiliate_key = global_sumup.sumup_affiliate_key or resolved_event_settings.sumup_affiliate_key or ""

    node_link = await fetch_nearest_node_sumup_link_for_event(
        conn=conn, event_node=event_node, environment=resolved_environment
    )
    if node_link is not None:
        if node_link.auth_method == SumUpAuthMethod.api_key and node_link.api_key is not None:
            return ResolvedSumUpAccess(
                source=SumUpConnectionSource.node_link,
                environment=resolved_environment,
                auth_method=SumUpAuthMethod.api_key,
                source_node_id=node_link.node_id,
                source_node_name=node_link.node_name,
                merchant_code=node_link.merchant_code,
                merchant_name=node_link.merchant_name,
                api_key=node_link.api_key,
                affiliate_key=affiliate_key,
            )
        if (
            node_link.auth_method == SumUpAuthMethod.oauth
            and node_link.refresh_token is not None
            and global_sumup.sumup_oauth_client_id.strip() != ""
            and global_sumup.sumup_oauth_client_secret.strip() != ""
        ):
            return ResolvedSumUpAccess(
                source=SumUpConnectionSource.node_link,
                environment=resolved_environment,
                auth_method=SumUpAuthMethod.oauth,
                source_node_id=node_link.node_id,
                source_node_name=node_link.node_name,
                merchant_code=node_link.merchant_code,
                merchant_name=node_link.merchant_name,
                refresh_token=node_link.refresh_token,
                oauth_client_id=global_sumup.sumup_oauth_client_id,
                oauth_client_secret=global_sumup.sumup_oauth_client_secret,
                affiliate_key=affiliate_key,
            )

    if resolved_environment != SumUpEnvironment.live:
        return None
    if (
        resolved_event_settings.sumup_oauth_refresh_token.strip() != ""
        and resolved_event_settings.sumup_oauth_client_id.strip() != ""
        and resolved_event_settings.sumup_oauth_client_secret.strip() != ""
        and resolved_event_settings.sumup_merchant_code.strip() != ""
    ):
        return ResolvedSumUpAccess(
            source=SumUpConnectionSource.legacy_event_oauth,
            environment=SumUpEnvironment.live,
            auth_method=SumUpAuthMethod.oauth,
            source_node_id=event_node.id,
            source_node_name=event_node.name,
            merchant_code=resolved_event_settings.sumup_merchant_code,
            refresh_token=resolved_event_settings.sumup_oauth_refresh_token,
            oauth_client_id=resolved_event_settings.sumup_oauth_client_id,
            oauth_client_secret=resolved_event_settings.sumup_oauth_client_secret,
            affiliate_key=affiliate_key,
        )

    if (
        resolved_event_settings.sumup_api_key.strip() != ""
        and resolved_event_settings.sumup_merchant_code.strip() != ""
    ):
        return ResolvedSumUpAccess(
            source=SumUpConnectionSource.legacy_event_api_key,
            environment=SumUpEnvironment.live,
            auth_method=SumUpAuthMethod.api_key,
            source_node_id=event_node.id,
            source_node_name=event_node.name,
            merchant_code=resolved_event_settings.sumup_merchant_code,
            api_key=resolved_event_settings.sumup_api_key,
            affiliate_key=affiliate_key,
        )

    return None


async def create_sumup_api_for_node(
    conn: Connection,
    node_id: int,
    environment: SumUpEnvironment | None = None,
    api_factory: Callable[[str, str], SumUpApi] | None = None,
) -> tuple[SumUpApi, ResolvedSumUpAccess] | None:
    access = await resolve_sumup_access(conn=conn, node_id=node_id, environment=environment)
    if access is None:
        return None
    return await create_sumup_api_for_access(access=access, api_factory=api_factory)


async def create_sumup_api_for_access(
    access: ResolvedSumUpAccess,
    api_factory: Callable[[str, str], SumUpApi] | None = None,
) -> tuple[SumUpApi, ResolvedSumUpAccess] | None:
    """Create a provider client from resolved settings without requiring a database connection."""
    create_api = api_factory or (lambda merchant_code, api_key: SumUpApi(api_key=api_key, merchant_code=merchant_code))
    if access.api_key is not None:
        return create_api(access.merchant_code, access.api_key), access
    if not access.is_oauth:
        return None
    assert access.oauth_client_id is not None
    assert access.oauth_client_secret is not None
    token = await fetch_new_oauth_token(
        client_id=access.oauth_client_id,
        client_secret=access.oauth_client_secret,
        refresh_token=access.refresh_token,
    )
    if token is None:
        return None
    return create_api(access.merchant_code, token.access_token), access


async def enrich_event_sumup_settings(
    conn: Connection, *, node_id: int, event_settings: RestrictedEventSettings
) -> RestrictedEventSettings:
    global_sumup = await fetch_global_sumup_config(conn=conn)
    event_node = await fetch_event_node_for_node(conn=conn, node_id=node_id)
    assert event_node is not None

    event_settings.sumup_global_oauth_configured = bool(
        global_sumup.sumup_oauth_client_id.strip() and global_sumup.sumup_oauth_client_secret.strip()
    )
    event_settings.sumup_global_affiliate_key_configured = bool(global_sumup.sumup_affiliate_key.strip())
    event_settings.sumup_legacy_api_key_configured = bool(
        event_settings.sumup_api_key.strip() and event_settings.sumup_merchant_code.strip()
    )
    event_settings.sumup_legacy_oauth_configured = bool(
        event_settings.sumup_oauth_refresh_token.strip()
        and event_settings.sumup_oauth_client_id.strip()
        and event_settings.sumup_oauth_client_secret.strip()
        and event_settings.sumup_merchant_code.strip()
    )

    access = await resolve_sumup_access(conn=conn, node_id=node_id)
    if access is None:
        event_settings.resolved_sumup_link = None
        return event_settings

    event_settings.resolved_sumup_link = ResolvedSumUpLink(
        source=access.source,
        environment=access.environment,
        auth_method=access.auth_method,
        source_node_id=access.source_node_id,
        source_node_name=access.source_node_name,
        merchant_code=access.merchant_code,
        merchant_name=access.merchant_name,
        inherited=access.source == SumUpConnectionSource.node_link and access.source_node_id != event_node.id,
    )
    return event_settings


async def resolve_terminal_sumup_access(
    conn: Connection, *, node_id: int, event_settings: RestrictedEventSettings | None = None
) -> ResolvedSumUpAccess | None:
    return await resolve_sumup_access(conn=conn, node_id=node_id, event_settings=event_settings)


async def fetch_node_or_raise(conn: Connection, node_id: int) -> Node:
    node = await fetch_node(conn=conn, node_id=node_id)
    if node is None:
        raise InvalidArgument("Node not found")
    return node
