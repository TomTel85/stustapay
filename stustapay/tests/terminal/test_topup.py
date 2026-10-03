# pylint: disable=attribute-defined-outside-init,unexpected-keyword-arg,missing-kwoa
import asyncio
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import asyncpg
import pytest
from sftkit.error import InvalidArgument

from stustapay.core.schema.account import AccountType
from stustapay.core.schema.order import CompletedTopUp, NewTopUp, PaymentMethod
from stustapay.core.schema.till import NewTillProfile, Till, TillLayout
from stustapay.core.schema.tree import Node, RestrictedEventSettings
from stustapay.core.service.order import OrderService
from stustapay.core.service.order.order import (
    TillPermissionException,
)
from stustapay.core.service.order.pending_order import (
    fetch_order_by_uuid,
    fetch_pending_online_topup_for_customer,
    save_pending_topup,
)
from stustapay.core.service.till.till import TillService
from stustapay.payment.sumup.api import SumUpOAuthToken
from stustapay.tests.sumup_mock import MockSumUpApi

from ..conftest import Cashier
from .conftest import (
    AssertAccountBalance,
    AssertSystemAccountBalance,
    AssignCashRegister,
    Customer,
    GetAccountBalance,
    GetSystemAccountBalance,
    LoginSupervisedUser,
)

START_BALANCE = 100


async def test_topup_exceeding_max_limit_fails(
    order_service: OrderService,
    event: RestrictedEventSettings,
    terminal_token: str,
    customer: Customer,
    login_supervised_user: LoginSupervisedUser,
    cashier: Cashier,
):
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    max_limit = event.max_account_balance
    new_topup = NewTopUp(
        uuid=uuid.uuid4(),
        amount=max_limit + 1,
        payment_method=PaymentMethod.cash,
        customer_tag_uid=customer.tag.uid,
    )
    with pytest.raises(InvalidArgument):
        await order_service.check_topup(token=terminal_token, new_topup=new_topup)


async def test_topup_sumup_order_flow(
    order_service: OrderService,
    till_service: TillService,
    terminal_token: str,
    assert_system_account_balance: AssertSystemAccountBalance,
    customer: Customer,
    login_supervised_user: LoginSupervisedUser,
    cashier: Cashier,
):
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    new_topup = NewTopUp(
        uuid=uuid.uuid4(),
        amount=20,
        payment_method=PaymentMethod.sumup,
        customer_tag_uid=customer.tag.uid,
    )
    pending_topup = await order_service.check_topup(
        token=terminal_token,
        new_topup=new_topup,
    )
    assert pending_topup.old_balance == START_BALANCE
    assert pending_topup.amount == 20
    assert pending_topup.new_balance == START_BALANCE + pending_topup.amount
    completed_topup = await order_service.book_topup(token=terminal_token, new_topup=new_topup)
    assert completed_topup is not None
    assert completed_topup.uuid == new_topup.uuid
    assert completed_topup.old_balance == START_BALANCE
    assert completed_topup.amount == 20
    assert completed_topup.new_balance == START_BALANCE + completed_topup.amount
    await assert_system_account_balance(account_type=AccountType.sumup_entry, expected_balance=-20)
    customer_info = await till_service.get_customer(token=terminal_token, customer_tag_uid=customer.tag.uid)
    assert customer_info.balance == completed_topup.new_balance


async def test_topup_deferred_sumup_order_flow(
    order_service: OrderService,
    till_service: TillService,
    terminal_token: str,
    assert_system_account_balance: AssertSystemAccountBalance,
    customer: Customer,
    login_supervised_user: LoginSupervisedUser,
    cashier: Cashier,
):
    # pylint: disable=protected-access
    order_service.sumup._create_sumup_api = lambda merchant_code, api_key: MockSumUpApi(api_key, merchant_code)  # type: ignore
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    new_topup = NewTopUp(
        uuid=uuid.uuid4(),
        amount=20,
        payment_method=PaymentMethod.sumup,
        customer_tag_uid=customer.tag.uid,
    )
    pending_topup = await order_service.check_topup(
        token=terminal_token,
        new_topup=new_topup,
    )
    assert pending_topup.old_balance == START_BALANCE
    assert pending_topup.amount == 20
    assert pending_topup.new_balance == START_BALANCE + pending_topup.amount
    MockSumUpApi.mock_amount(pending_topup.amount)
    completed_topup = await order_service.book_topup(token=terminal_token, new_topup=new_topup, pending=True)
    assert completed_topup is not None
    assert completed_topup.uuid == new_topup.uuid
    assert completed_topup.old_balance == START_BALANCE
    assert completed_topup.amount == 20
    assert completed_topup.new_balance == START_BALANCE + completed_topup.amount
    customer_info = await till_service.get_customer(token=terminal_token, customer_tag_uid=customer.tag.uid)
    assert customer_info.balance == START_BALANCE
    completed_topup = await order_service.check_pending_topup(token=terminal_token, order_uuid=pending_topup.uuid)
    assert completed_topup is not None
    assert completed_topup.uuid == new_topup.uuid
    assert completed_topup.old_balance == START_BALANCE
    assert completed_topup.amount == 20
    assert completed_topup.new_balance == START_BALANCE + completed_topup.amount
    await assert_system_account_balance(account_type=AccountType.sumup_entry, expected_balance=-20)
    customer_info = await till_service.get_customer(token=terminal_token, customer_tag_uid=customer.tag.uid)
    assert customer_info.balance == completed_topup.new_balance


async def test_only_topup_till_profiles_can_topup(
    till_service: TillService,
    order_service: OrderService,
    event_admin_token: str,
    event_node: Node,
    till_layout: TillLayout,
    till: Till,
    terminal_token: str,
    customer: Customer,
    cashier: Cashier,
    login_supervised_user: LoginSupervisedUser,
):
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    profile = await till_service.profile.create_profile(
        token=event_admin_token,
        node_id=event_node.id,
        profile=NewTillProfile(
            name="profile2",
            description="",
            layout_id=till_layout.id,
            allow_top_up=False,
            allow_cash_out=False,
            allow_ticket_sale=False,
            allow_ticket_vouchers=False,
            enable_ssp_payment=True,
            enable_cash_payment=False,
            enable_card_payment=False,
        ),
    )
    till.active_profile_id = profile.id
    await till_service.update_till(token=event_admin_token, node_id=event_node.id, till_id=till.id, till=till)

    with pytest.raises(TillPermissionException):
        new_topup = NewTopUp(
            uuid=uuid.uuid4(),
            amount=20,
            payment_method=PaymentMethod.cash,
            customer_tag_uid=customer.tag.uid,
        )
        await order_service.check_topup(token=terminal_token, new_topup=new_topup)


async def test_topup_cash_order_flow(
    order_service: OrderService,
    cashier: Cashier,
    get_account_balance: GetAccountBalance,
    get_system_account_balance: GetSystemAccountBalance,
    customer: Customer,
    terminal_token: str,
    assert_system_account_balance: AssertSystemAccountBalance,
    assert_account_balance: AssertAccountBalance,
    login_supervised_user: LoginSupervisedUser,
    assign_cash_register: AssignCashRegister,
):
    cash_register_account_id = await assign_cash_register(cashier=cashier)
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    cash_drawer_start_balance = await get_account_balance(account_id=cash_register_account_id)
    cash_sale_source_start_balance = await get_system_account_balance(account_type=AccountType.cash_topup_source)
    cash_entry_start_balance = await get_system_account_balance(account_type=AccountType.cash_entry)

    new_topup = NewTopUp(
        uuid=uuid.uuid4(),
        amount=20,
        payment_method=PaymentMethod.cash,
        customer_tag_uid=customer.tag.uid,
    )
    pending_top_up = await order_service.check_topup(token=terminal_token, new_topup=new_topup)
    assert pending_top_up.old_balance == START_BALANCE
    assert pending_top_up.amount == 20
    assert pending_top_up.new_balance == START_BALANCE + pending_top_up.amount
    completed_topup = await order_service.book_topup(token=terminal_token, new_topup=new_topup)
    assert completed_topup is not None
    assert completed_topup.old_balance == START_BALANCE
    assert completed_topup.amount == 20
    assert completed_topup.new_balance == START_BALANCE + completed_topup.amount
    await assert_account_balance(account_id=cash_register_account_id, expected_balance=cash_drawer_start_balance + 20)
    await assert_system_account_balance(
        account_type=AccountType.cash_entry, expected_balance=cash_entry_start_balance - 20
    )
    await assert_system_account_balance(
        account_type=AccountType.cash_topup_source, expected_balance=cash_sale_source_start_balance - 20
    )


async def test_pending_online_topup_lookup_is_scoped_and_excludes_shared_orders(
    db_connection, event_node: Node, till: Till, customer: Customer
):
    async def save(account_id, method, status="pending", shared=False):
        topup = CompletedTopUp(
            uuid=uuid.uuid4(),
            payment_method=method,
            customer_tag_uid=customer.tag.uid,
            customer_account_id=account_id,
            amount=20,
            old_balance=100,
            new_balance=120,
            booked_at=datetime.now(timezone.utc),
            cashier_id=None,
            till_id=till.id,
        )
        await save_pending_topup(
            conn=db_connection, till_id=till.id, node_id=event_node.id, cashier_id=None, topup=topup
        )
        await db_connection.execute("update pending_sumup_order set status = $2 where uuid = $1", topup.uuid, status)
        if shared:
            await db_connection.execute(
                "insert into shared_topup_order (order_uuid, customer_account_id, contributor_name) values ($1, $2, 'Guest')",
                topup.uuid,
                customer.account_id,
            )
        return topup.uuid

    try:
        await save(customer.account_id, PaymentMethod.sumup_online)
        expected = await save(customer.account_id, PaymentMethod.sumup_online)
        await save(customer.account_id + 100000, PaymentMethod.sumup_online)
        await save(customer.account_id, PaymentMethod.sumup)
        await save(customer.account_id, PaymentMethod.sumup_online, status="booked")
        await save(customer.account_id, PaymentMethod.sumup_online, shared=True)
        pending = await fetch_pending_online_topup_for_customer(db_connection, customer.account_id)
        assert pending is not None and pending.uuid == expected
        assert await fetch_pending_online_topup_for_customer(db_connection, -1) is None
        assert await db_connection.fetchval(
            "select exists(select from pg_indexes where indexname = 'pending_online_topup_customer_idx')"
        )
    finally:
        # The session-scoped test database is shared with customer-portal tests.
        await db_connection.execute("delete from pending_sumup_order where node_id = $1", event_node.id)


@pytest.mark.parametrize("mode", ["single", "retry", "concurrent", "oauth"])
async def test_payment_worker_releases_connection_and_books_once(
    order_service: OrderService,
    terminal_token: str,
    customer: Customer,
    login_supervised_user: LoginSupervisedUser,
    cashier: Cashier,
    db_connection,
    monkeypatch,
    mode: str,
):
    # pylint: disable=protected-access
    service = order_service.sumup
    monkeypatch.setattr(
        service, "_create_sumup_api", lambda merchant_code, api_key: MockSumUpApi(api_key, merchant_code)
    )
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    topup = NewTopUp(
        uuid=uuid.uuid4(), amount=20, payment_method=PaymentMethod.sumup, customer_tag_uid=customer.tag.uid
    )
    MockSumUpApi.mock_amount(20)
    await order_service.book_topup(token=terminal_token, new_topup=topup, pending=True)
    pending = await fetch_order_by_uuid(db_connection, topup.uuid)
    api = MockSumUpApi("unused", "TEST_MERCHANT")
    original_find = api.find_checkout

    async def find(order_uuid):
        if mode != "concurrent":
            assert service.db_pool.get_size() - service.db_pool.get_idle_size() == 1
        return await original_find(order_uuid)

    find_spy = AsyncMock(side_effect=find)
    monkeypatch.setattr(api, "find_checkout", find_spy)
    monkeypatch.setattr(service, "_create_sumup_api", lambda merchant_code, api_key: api)
    token_spy = None
    if mode == "oauth":
        access = await service._resolve_worker_sumup_access(pending_order=pending)
        access = replace(
            access, api_key=None, refresh_token="refresh", oauth_client_id="client", oauth_client_secret="secret"
        )
        monkeypatch.setattr(service, "_resolve_worker_sumup_access", AsyncMock(return_value=access))

        async def fetch_token(**_kwargs):
            assert service.db_pool.get_size() - service.db_pool.get_idle_size() == 1
            return SumUpOAuthToken(
                token_type="Bearer",
                access_token="access",
                refresh_token="refresh",
                expires_in=300,
                expires_at=datetime.now(timezone.utc),
            )

        token_spy = AsyncMock(side_effect=fetch_token)
        monkeypatch.setattr("stustapay.core.service.sumup_link.fetch_new_oauth_token", token_spy)
    original_book = service._book_paid_pending_order
    transaction_ids = []

    async def book(*, conn, pending_order):
        transaction_ids.append(await conn.fetchval("select txid_current()"))
        if mode == "retry" and len(transaction_ids) == 1:
            raise asyncpg.exceptions.SerializationError("retry transaction")
        return await original_book(conn=conn, pending_order=pending_order)

    monkeypatch.setattr(service, "_book_paid_pending_order", book)
    if mode == "concurrent":
        await asyncio.gather(
            service._process_pending_order_in_worker(pending), service._process_pending_order_in_worker(pending)
        )
    else:
        await service._process_pending_order_in_worker(pending)
    if token_spy is not None:
        token_spy.assert_awaited_once()
    assert find_spy.await_count == (2 if mode == "concurrent" else 1)
    assert len(transaction_ids) == (2 if mode == "retry" else 1)
    assert len(set(transaction_ids)) == len(transaction_ids)

    # A stale pending row must be reconciled from the local ledger without requiring
    # merchant credentials, OAuth renewal, or another checkout status request.
    await db_connection.execute(
        "update pending_sumup_order set status = 'pending', created_at = now() - interval '1 hour' where uuid = $1",
        topup.uuid,
    )
    resolve_spy = AsyncMock(side_effect=RuntimeError("Merchant connection unavailable"))
    monkeypatch.setattr(service, "_resolve_worker_sumup_access", resolve_spy)
    find_spy.side_effect = RuntimeError("SumUp unavailable")
    await service._process_pending_order_in_worker(pending)
    resolve_spy.assert_not_awaited()
    assert find_spy.await_count == (2 if mode == "concurrent" else 1)
    if token_spy is not None:
        token_spy.assert_awaited_once()
    assert await db_connection.fetchval("select status from pending_sumup_order where uuid = $1", topup.uuid) == "booked"
    assert await db_connection.fetchval("select count(*) from ordr where uuid = $1", topup.uuid) == 1
    assert await db_connection.fetchval("select balance from account where id = $1", customer.account_id) == 120
