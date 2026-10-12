import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sftkit.database import Connection
from sftkit.error import AccessDenied

from stustapay.administration.routers.mdm import (
    CreateHeadwindMappingPayload,
    create_or_update_mapping,
    delete_mapping,
    list_headwind_devices,
    refresh_mapping_token,
)
from stustapay.administration.service import HeadwindClient
from stustapay.core.http.context import Context
from stustapay.core.schema.terminal import NewTerminal, TerminalLoginMode
from stustapay.core.schema.tree import NewNode, Node
from stustapay.core.service.common.error import NodeIsReadOnly
from stustapay.core.service.terminal import TerminalService
from stustapay.core.service.tree.service import TreeService


@pytest.mark.parametrize("action", ["list", "map", "delete", "refresh"])
async def test_headwind_management_rejects_child_scope_before_service_or_mdm_calls(action):
    service = AsyncMock()
    client = AsyncMock()
    kwargs: dict[str, Any] = {"token": "event-token", "terminal_service": service, "node_id": 42}
    with pytest.raises(HTTPException) as exc:
        if action == "list":
            await list_headwind_devices(**kwargs, headwind_client=client)
        elif action == "map":
            await create_or_update_mapping(
                **kwargs,
                payload=CreateHeadwindMappingPayload(terminal_id=1, headwind_device_id="1"),
                headwind_client=client,
            )
        elif action == "delete":
            await delete_mapping(**kwargs, terminal_id=1)
        else:
            await refresh_mapping_token(**kwargs, terminal_id=1, headwind_client=client)
    assert exc.value.status_code == 403
    assert service.mock_calls == []
    assert client.mock_calls == []


async def test_headwind_inventory_requires_root_privilege_before_external_request():
    service = AsyncMock()
    service.list_headwind_mappings.side_effect = AccessDenied("missing root privilege")
    client = AsyncMock()
    with pytest.raises(AccessDenied):
        await list_headwind_devices(token="event-token", terminal_service=service, node_id=0, headwind_client=client)
    assert client.mock_calls == []


async def test_root_mapping_uses_terminal_event_wifi():
    service = AsyncMock()
    mapping = SimpleNamespace(id=2, headwind_device_id="device", terminal_name="POS")
    mapping.model_copy = lambda update: update
    service.upsert_headwind_mapping.return_value = mapping
    service.issue_headwind_terminal_token.return_value = ("terminal-token", SimpleNamespace(name="POS", node_id=42))
    client = SimpleNamespace(enabled=True, update_device_custom_attributes=AsyncMock())
    tree = SimpleNamespace(
        get_restricted_event_settings=AsyncMock(
            return_value=SimpleNamespace(wifi_ssid="event-wifi", wifi_passphrase="secret")
        )
    )
    context = SimpleNamespace(tree_service=tree, config=SimpleNamespace(terminalserver=SimpleNamespace(base_url="url")))
    await create_or_update_mapping(
        payload=CreateHeadwindMappingPayload(terminal_id=1, headwind_device_id="device"),
        token="root-token",
        terminal_service=service,
        node_id=0,
        headwind_client=cast(HeadwindClient, client),
        context=cast(Context, context),
    )
    tree.get_restricted_event_settings.assert_awaited_once_with(token="root-token", node_id=42)
    assert "event-wifi" in client.update_device_custom_attributes.call_args.kwargs["custom3"]


@pytest.mark.parametrize("action", ["map", "refresh"])
@pytest.mark.parametrize("at_event", [True, False])
@pytest.mark.parametrize("with_wifi", [True, False])
async def test_root_headwind_provisions_event_terminals(
    terminal_service: TerminalService,
    tree_service: TreeService,
    global_admin_token: str,
    event_node: Node,
    db_connection: Connection,
    action: str,
    at_event: bool,
    with_wifi: bool,
):
    assert event_node.event is not None
    if with_wifi:
        await db_connection.execute(
            "update event set wifi_ssid = 'event-wifi', wifi_passphrase = 'event-secret' where id = $1",
            event_node.event.id,
        )
    node_id = event_node.id
    if not at_event:
        node = await tree_service.create_node(
            token=global_admin_token,
            node_id=event_node.id,
            new_node=NewNode(name="Shared devices", description=""),
        )
        node_id = node.id
    terminal = await terminal_service.create_terminal(
        token=global_admin_token,
        node_id=node_id,
        terminal=NewTerminal(name="Shared POS", login_mode=TerminalLoginMode.personal),
    )
    client = SimpleNamespace(enabled=True, update_device_custom_attributes=AsyncMock())
    context = SimpleNamespace(
        tree_service=tree_service,
        config=SimpleNamespace(terminalserver=SimpleNamespace(base_url="https://terminal.example")),
    )
    kwargs: dict[str, Any] = {
        "token": global_admin_token,
        "terminal_service": terminal_service,
        "node_id": 0,
        "headwind_client": client,
        "context": context,
    }
    mapping = await create_or_update_mapping(
        **kwargs,
        payload=CreateHeadwindMappingPayload(terminal_id=terminal.id, headwind_device_id=f"device-{terminal.id}"),
    )
    first_token = client.update_device_custom_attributes.call_args.kwargs["custom1"]
    if action == "refresh":
        client.update_device_custom_attributes.reset_mock()
        mapping = await refresh_mapping_token(**kwargs, terminal_id=terminal.id)
        assert client.update_device_custom_attributes.call_args.kwargs["custom1"] != first_token

    client.update_device_custom_attributes.assert_awaited_once()
    pushed = client.update_device_custom_attributes.call_args.kwargs
    assert pushed["custom1"]
    assert pushed["custom2"] == "https://terminal.example"
    assert mapping.last_push_status == "success"
    if with_wifi:
        assert json.loads(pushed["custom3"]) == {
            "terminal_name": terminal.name,
            "wifi_ssid": "event-wifi",
            "wifi_passphrase": "event-secret",
        }
        assert mapping.last_wifi_push_status == "success"
        assert mapping.last_wifi_pushed_at is not None
    else:
        assert pushed["custom3"] == terminal.name
        assert mapping.last_wifi_pushed_at is None
    await delete_mapping(
        token=global_admin_token, terminal_service=terminal_service, node_id=0, terminal_id=terminal.id
    )
    assert (
        await terminal_service.get_headwind_mapping_with_terminal(
            token=global_admin_token, node_id=0, terminal_id=terminal.id
        )
        is None
    )


@pytest.mark.parametrize("action", ["map", "refresh", "delete", "issue", "token_result", "wifi_result"])
@pytest.mark.parametrize("at_event", [True, False])
async def test_root_headwind_rejects_archived_terminal_mutations(
    terminal_service: TerminalService,
    tree_service: TreeService,
    global_admin_token: str,
    event_node: Node,
    db_connection: Connection,
    action: str,
    at_event: bool,
):
    node_id = event_node.id
    if not at_event:
        child = await tree_service.create_node(
            token=global_admin_token,
            node_id=node_id,
            new_node=NewNode(name="Archived devices", description=""),
        )
        node_id = child.id
    terminal = await terminal_service.create_terminal(
        token=global_admin_token,
        node_id=node_id,
        terminal=NewTerminal(name="Archived POS", login_mode=TerminalLoginMode.personal),
    )
    client = SimpleNamespace(enabled=True, update_device_custom_attributes=AsyncMock())
    context = SimpleNamespace(
        tree_service=tree_service,
        config=SimpleNamespace(terminalserver=SimpleNamespace(base_url="https://terminal.example")),
    )
    kwargs: dict[str, Any] = {
        "token": global_admin_token,
        "terminal_service": terminal_service,
        "node_id": 0,
        "headwind_client": client,
        "context": context,
    }
    payload = CreateHeadwindMappingPayload(terminal_id=terminal.id, headwind_device_id=f"device-{terminal.id}")
    mapping = await create_or_update_mapping(**kwargs, payload=payload)
    client.update_device_custom_attributes.reset_mock()
    await tree_service.archive_node(token=global_admin_token, node_id=event_node.id)
    before = await db_connection.fetchrow("select * from terminal where id = $1", terminal.id)
    mapping_before = await terminal_service.get_headwind_mapping_with_terminal(
        token=global_admin_token, node_id=0, terminal_id=terminal.id
    )

    with pytest.raises(NodeIsReadOnly):
        if action == "map":
            await create_or_update_mapping(**kwargs, payload=payload)
        elif action == "refresh":
            await refresh_mapping_token(**kwargs, terminal_id=terminal.id)
        elif action == "delete":
            await delete_mapping(
                token=global_admin_token, terminal_service=terminal_service, node_id=0, terminal_id=terminal.id
            )
        elif action == "issue":
            await terminal_service.issue_headwind_terminal_token(
                token=global_admin_token, node_id=0, terminal_id=terminal.id
            )
        else:
            record_result = (
                terminal_service.record_headwind_push_result
                if action == "token_result"
                else terminal_service.record_headwind_wifi_push_result
            )
            await record_result(
                token=global_admin_token, node_id=0, mapping_id=mapping.id, success=False, error_message="x"
            )

    client.update_device_custom_attributes.assert_not_awaited()
    assert await db_connection.fetchrow("select * from terminal where id = $1", terminal.id) == before
    assert (
        await terminal_service.get_headwind_mapping_with_terminal(
            token=global_admin_token, node_id=0, terminal_id=terminal.id
        )
        == mapping_before
    )
