# pylint: disable=redefined-outer-name,unexpected-keyword-arg,missing-kwoa,unused-import
from uuid import uuid4

import pytest
from sftkit.error import AccessDenied, InvalidArgument, NotFound

from stustapay.core.schema.order import Button, NewSale, PaymentMethod
from stustapay.core.schema.terminal import NewTerminal, TerminalLoginMode, UpdateTerminal
from stustapay.core.schema.tree import CopyEventOptions, CopyEventRequest
from stustapay.core.schema.user import UserTag
from stustapay.core.service.cashier import CloseOut
from stustapay.tests.terminal.test_sale import sale_products  # noqa: F401


async def configure(terminal_service, token, node, terminal, role_id, register_id=None, login_mode="device"):
    return await terminal_service.update_terminal(
        token=token,
        node_id=node.id,
        terminal_id=terminal.id,
        terminal=NewTerminal(
            name=terminal.name, login_mode=login_mode, device_role_id=role_id, device_cash_register_id=register_id
        ),
    )


async def test_device_identity_and_personal_login_guards(
    terminal_service,
    user_service,
    db_connection,
    terminal,
    terminal_token,
    event_node,
    event_admin_token,
    cashier,
    event_admin_tag,
):
    assert terminal.login_mode == TerminalLoginMode.personal
    managed = await configure(terminal_service, event_admin_token, event_node, terminal, cashier.cashier_role.id)
    assert managed.device_user_id == managed.active_user_id
    user = await terminal_service.get_current_user(token=terminal_token)
    assert user.is_device_identity
    assert user.display_name == f"Gerät: {terminal.name}"
    credentials = await db_connection.fetchrow("select password, user_tag_id from usr where id = $1", user.id)
    assert credentials["password"] is None and credentials["user_tag_id"] is None
    assert user.id not in {u.id for u in await user_service.list_users(token=event_admin_token, node_id=event_node.id)}
    with pytest.raises(NotFound):
        await user_service.get_user(token=event_admin_token, node_id=event_node.id, user_id=user.id)
    with pytest.raises(AccessDenied):
        await user_service.login_user(username=user.login, password="anything")
    with pytest.raises(AccessDenied):
        await terminal_service.login_user(
            token=terminal_token, user_tag=UserTag(uid=event_admin_tag.uid), user_role_id=0
        )
    with pytest.raises(AccessDenied):
        await terminal_service.check_user_login(token=terminal_token, user_tag=UserTag(uid=event_admin_tag.uid))
    with pytest.raises(AccessDenied):
        await terminal_service.logout_user(token=terminal_token)
    with pytest.raises(InvalidArgument):
        await terminal_service.force_logout_user(
            token=event_admin_token, node_id=event_node.id, terminal_id=terminal.id
        )
    with pytest.raises(AccessDenied):
        await terminal_service.login_user_to_terminal(
            token=event_admin_token,
            node_id=event_node.id,
            terminal_id=terminal.id,
            user_id=cashier.id,
            role_id=cashier.cashier_role.id,
        )
    config = await terminal_service.get_terminal_config(token=terminal_token)
    assert config.login_mode == TerminalLoginMode.device
    assert config.active_user_id == user.id
    # A fresh token/config request never creates another identity.
    again = await configure(terminal_service, event_admin_token, event_node, terminal, cashier.cashier_role.id)
    assert again.device_user_id == user.id
    await configure(terminal_service, event_admin_token, event_node, terminal, None, login_mode="personal")
    assert await terminal_service.get_current_user(token=terminal_token) is None
    with pytest.raises(AccessDenied):
        await terminal_service.login_user_to_terminal(
            token=event_admin_token,
            node_id=event_node.id,
            terminal_id=terminal.id,
            user_id=user.id,
            role_id=cashier.cashier_role.id,
        )
    await terminal_service.login_user(token=terminal_token, user_tag=UserTag(uid=event_admin_tag.uid), user_role_id=0)
    assert not (await terminal_service.get_current_user(token=terminal_token)).is_device_identity
    again = await configure(terminal_service, event_admin_token, event_node, terminal, cashier.cashier_role.id)
    assert again.device_user_id == user.id


async def test_device_sales_and_central_role_changes(
    terminal_service,
    user_service,
    order_service,
    db_connection,
    terminal,
    terminal_token,
    event_node,
    event_admin_token,
    cashier,
    customer,
    sale_products,  # noqa: F811
):
    managed = await configure(terminal_service, event_admin_token, event_node, terminal, cashier.cashier_role.id)
    sale = NewSale(
        uuid=uuid4(),
        buttons=[Button(till_button_id=sale_products.beer_button.id, quantity=1)],
        customer_tag_uid=customer.tag.uid,
        payment_method=PaymentMethod.tag,
    )
    order = await order_service.book_sale(token=terminal_token, new_sale=sale)
    assert await db_connection.fetchval("select cashier_id from ordr where id = $1", order.id) == managed.device_user_id
    await user_service.update_user_role_privileges(
        token=event_admin_token,
        node_id=event_node.id,
        role_id=cashier.cashier_role.id,
        is_privileged=False,
        privileges=[],
    )
    assert (await terminal_service.get_current_user(token=terminal_token)).privileges == []
    with pytest.raises(AccessDenied):
        await order_service.book_sale(token=terminal_token, new_sale=sale.model_copy(update={"uuid": uuid4()}))
    await configure(terminal_service, event_admin_token, event_node, terminal, None, login_mode="personal")
    await terminal_service.delete_terminal(token=event_admin_token, node_id=event_node.id, terminal_id=terminal.id)
    assert await db_connection.fetchval("select is_device_identity from usr where id = $1", managed.device_user_id)
    assert await db_connection.fetchval("select cashier_id from ordr where id = $1", order.id) == managed.device_user_id


async def test_device_drawer_lifecycle(
    terminal_service,
    cashier_service,
    till_service,
    db_connection,
    terminal,
    terminal_token,
    event_node,
    event_admin_token,
    event_admin_user,
    cashier,
    cash_register,
    till,
):
    managed = await configure(
        terminal_service, event_admin_token, event_node, terminal, cashier.cashier_role.id, cash_register.id
    )

    async def shift_starts():
        return await db_connection.fetchval(
            "select count(*) from ordr where cashier_id = $1 and order_type = 'cashier_shift_start'",
            managed.device_user_id,
        )

    assert await shift_starts() == 1
    await configure(
        terminal_service, event_admin_token, event_node, terminal, cashier.cashier_role.id, cash_register.id
    )
    await terminal_service.get_terminal_config(token=terminal_token)
    assert await shift_starts() == 1
    assert (
        await db_connection.fetchval("select active_cash_register_id from till where id = $1", till.id)
        == cash_register.id
    )
    with pytest.raises(InvalidArgument, match="Close"):
        await configure(terminal_service, event_admin_token, event_node, terminal, None, login_mode="personal")
    with pytest.raises(InvalidArgument, match="Close"):
        await configure(terminal_service, event_admin_token, event_node, terminal, cashier.cashier_role.id)
    with pytest.raises(InvalidArgument, match="Close"):
        await terminal_service.delete_terminal(token=event_admin_token, node_id=event_node.id, terminal_id=terminal.id)
    with pytest.raises(InvalidArgument):
        await till_service.register.assign_cash_register_admin(
            token=event_admin_token,
            node_id=event_node.id,
            cashier_id=cashier.id,
            cash_register_id=cash_register.id,
        )
    result = await cashier_service.close_out_cashier(
        token=event_admin_token,
        node_id=event_node.id,
        cashier_id=managed.device_user_id,
        close_out=CloseOut(
            comment="Device shift", actual_cash_drawer_balance=0, closing_out_user_id=event_admin_user[0].id
        ),
    )
    assert result.imbalance == 0
    refreshed = await terminal_service.get_terminal(
        token=event_admin_token, node_id=event_node.id, terminal_id=terminal.id
    )
    assert refreshed.device_cash_register_id is None
    assert refreshed.active_user_id == managed.device_user_id
    assert await db_connection.fetchval("select active_cash_register_id from till where id = $1", till.id) is None
    assert (
        len(
            await cashier_service.get_cashier_shifts(
                token=event_admin_token,
                node_id=event_node.id,
                cashier_id=managed.device_user_id,
            )
        )
        == 1
    )
    await configure(
        terminal_service, event_admin_token, event_node, terminal, cashier.cashier_role.id, cash_register.id
    )
    assert await shift_starts() == 2


async def test_device_role_required_and_creation(terminal_service, event_admin_token, event_node, cashier):
    with pytest.raises(AccessDenied):
        await terminal_service.create_terminal(
            token=event_admin_token,
            node_id=event_node.id,
            terminal=NewTerminal(name="Missing role"),
        )
    created = await terminal_service.create_terminal(
        token=event_admin_token,
        node_id=event_node.id,
        terminal=NewTerminal(name="Device", device_role_id=cashier.cashier_role.id),
    )
    assert created.login_mode == TerminalLoginMode.device
    registration = await terminal_service.register_terminal(registration_uuid=created.registration_uuid)
    user = await terminal_service.get_current_user(token=registration.token)
    assert user.id == created.device_user_id


@pytest.mark.parametrize("payload_type", [NewTerminal, UpdateTerminal])
@pytest.mark.parametrize("device_mode", [False, True])
async def test_edit_without_login_mode_preserves_identity(
    terminal_service, terminal, event_node, event_admin_token, cashier, cash_register, till, payload_type, device_mode
):
    assert till.terminal_id == terminal.id
    original = terminal
    if device_mode:
        original = await configure(
            terminal_service, event_admin_token, event_node, terminal, cashier.cashier_role.id, cash_register.id
        )
    updated = await terminal_service.update_terminal(
        token=event_admin_token,
        node_id=event_node.id,
        terminal_id=terminal.id,
        terminal=payload_type(name="Renamed terminal"),
    )
    assert updated.name == "Renamed terminal"
    assert updated.login_mode == original.login_mode
    assert updated.device_user_id == original.device_user_id
    assert updated.active_user_id == original.active_user_id
    assert updated.device_role_id == original.device_role_id
    assert updated.device_cash_register_id == original.device_cash_register_id


async def test_copy_event_excludes_device_identities(
    terminal_service, tree_service, db_connection, terminal, event_node, event_admin_token, global_admin_token, cashier
):
    managed = await configure(terminal_service, event_admin_token, event_node, terminal, cashier.cashier_role.id)
    personal_users = await db_connection.fetchval(
        "select count(*) from usr where node_id = $1 and not is_device_identity", event_node.id
    )
    copied = await tree_service.copy_event(
        token=global_admin_token,
        node_id=event_node.id,
        request=CopyEventRequest(name="Device event copy", description="", options=CopyEventOptions()),
    )
    assert await db_connection.fetchval("select count(*) from usr where node_id = $1", copied.id) == personal_users
    copied_terminals = await terminal_service.list_terminals(token=global_admin_token, node_id=copied.id)
    assert copied_terminals
    assert all(t.login_mode == TerminalLoginMode.personal and t.device_user_id is None for t in copied_terminals)
    assert await db_connection.fetchval("select is_device_identity from usr where id = $1", managed.device_user_id)
