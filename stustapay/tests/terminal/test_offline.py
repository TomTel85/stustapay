# ruff: noqa: F811
# pylint: disable=redefined-outer-name,unused-argument,unexpected-keyword-arg,missing-kwoa,unused-import
"""Offline journal integration tests exercise the real transaction and snapshot boundary."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sftkit.error import InvalidArgument

from stustapay.core.schema.offline import OfflineBooking, OfflineBookingStatus, OfflineImport
from stustapay.core.schema.order import Button, NewSale, NewTopUp, PaymentMethod
from stustapay.core.schema.product import NewProduct
from stustapay.core.schema.till import NewTillButton, NewTillLayout
from stustapay.core.service.order.offline import check_offline_budget, offline_positions
from stustapay.tests.terminal.test_sale import sale_products  # noqa: F401


@pytest.fixture
async def prepared_offline(
    db_connection, order_service, terminal_token, event_node, cashier, login_supervised_user, sale_products, customer
):
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    await db_connection.execute("update event set offline_enabled=true where id=$1", event_node.event.id)
    return await order_service.prepare_offline(token=terminal_token)


@pytest.fixture
async def prepared_offline_with_free_price(
    db_connection,
    order_service,
    terminal_token,
    event_node,
    cashier,
    login_supervised_user,
    free_price_product,
    customer,
):
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    await db_connection.execute("update event set offline_enabled=true where id=$1", event_node.event.id)
    return await order_service.prepare_offline(token=terminal_token)


def sale_for(customer, sale_products, quantity=1):
    return NewSale(
        uuid=uuid4(),
        customer_tag_uid=customer.tag.uid,
        payment_method=PaymentMethod.tag,
        used_vouchers=0,
        buttons=[Button(till_button_id=sale_products.beer_button.id, quantity=quantity)],
    )


@pytest.fixture
async def free_price_product(
    product_service, till_service, event_admin_token, event_node, tax_rate_ust, till_layout, sale_products
):
    """A standalone variable-price product is eligible for offline tips."""
    product = await product_service.create_product(
        token=event_admin_token,
        node_id=event_node.id,
        product=NewProduct(
            name="Donation",
            price=None,
            fixed_price=False,
            tax_rate_id=tax_rate_ust.id,
            is_locked=True,
            is_returnable=False,
        ),
    )
    button = await till_service.layout.create_button(
        token=event_admin_token,
        node_id=event_node.id,
        button=NewTillButton(name="Donation", product_ids=[product.id]),
    )
    mixed_button = await till_service.layout.create_button(
        token=event_admin_token,
        node_id=event_node.id,
        button=NewTillButton(name="Mixed donation", product_ids=[product.id, sale_products.beer_product.id]),
    )
    await till_service.layout.update_layout(
        token=event_admin_token,
        node_id=event_node.id,
        layout_id=till_layout.id,
        layout=NewTillLayout(
            name=till_layout.name,
            description=till_layout.description,
            button_ids=[
                sale_products.deposit_button.id,
                sale_products.beer_button.id,
                sale_products.beer_button_full.id,
                button.id,
                mixed_button.id,
            ],
            ticket_ids=[],
        ),
    )
    return SimpleNamespace(product=product, button=button, mixed_button=mixed_button)


def free_price_sale(customer, free_price_product, price):
    return NewSale(
        uuid=uuid4(),
        customer_tag_uid=customer.tag.uid,
        payment_method=PaymentMethod.tag,
        used_vouchers=0,
        buttons=[Button(till_button_id=free_price_product.button.id, price=price)],
    )


async def test_offline_disabled_by_default(order_service, terminal_token, cashier, login_supervised_user):
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    with pytest.raises(InvalidArgument, match="disabled"):
        await order_service.prepare_offline(token=terminal_token)


async def test_online_journal_exact_replay_and_mismatch(
    order_service, terminal_token, customer, sale_products, cashier, login_supervised_user
):
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    sale = sale_for(customer, sale_products)
    first = await order_service.book_sale(token=terminal_token, new_sale=sale)
    second = await order_service.book_sale(token=terminal_token, new_sale=sale)
    assert first == second
    sale.buttons[0].quantity = 2
    with pytest.raises(InvalidArgument, match="different content"):
        await order_service.book_sale(token=terminal_token, new_sale=sale)


async def test_offline_snapshot_historical_price_idempotence_and_overdraft(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    db_connection,
    event_admin_token,
    event_node,
):
    snapshot = prepared_offline
    assert next(c for c in snapshot.customers if c.customer_tag_uid == customer.tag.uid).balance_cents > 0
    sale = sale_for(customer, sale_products)
    # Another disconnected till has already spent the funds; historical accepted sale must still book.
    await db_connection.execute("update account set balance=0 where id=$1", customer.account_id)
    await db_connection.execute("update product set price=9 where id=$1", sale_products.beer_product.id)
    booking = OfflineBooking(snapshot_id=snapshot.id, sale=sale, sequence=1, recorded_at=snapshot.server_time)
    payload = OfflineImport(bookings=[booking])
    first = await order_service.import_offline(token=terminal_token, payload=payload)
    result = first.results[0]
    assert result.status == OfflineBookingStatus.booked
    assert result.sale.total_price == 5
    assert result.sale.new_balance == -5
    second = await order_service.import_offline(token=terminal_token, payload=payload)
    assert second.results[0].status == OfflineBookingStatus.already_booked
    assert await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == -5
    status = await order_service.offline_booking_status(token=terminal_token, order_uuid=sale.uuid)
    assert status.sale.id == result.sale.id
    report = await order_service.offline_report(token=event_admin_token, node_id=event_node.id)
    assert report[0].new_balance == -5
    assert report[0].uuid == sale.uuid


async def test_lost_online_response_import_does_not_double_book(
    prepared_offline, order_service, terminal_token, customer, sale_products
):
    sale = sale_for(customer, sale_products)
    online = await order_service.book_sale(token=terminal_token, new_sale=sale)
    result = await order_service.import_offline(
        token=terminal_token,
        payload=OfflineImport(
            bookings=[
                OfflineBooking(
                    snapshot_id=prepared_offline.id, sale=sale, sequence=1, recorded_at=prepared_offline.server_time
                )
            ]
        ),
    )
    assert result.results[0].status == OfflineBookingStatus.already_booked
    assert result.results[0].sale == online


async def test_online_topup_after_snapshot_is_preserved_when_offline_sale_imported(
    prepared_offline,
    order_service,
    terminal_token,
    customer,
    sale_products,
    db_connection,
    cashier,
    assign_cash_register,
    login_supervised_user,
):
    snapshot = prepared_offline
    initial_balance = await db_connection.fetchval("select balance from account where id=$1", customer.account_id)
    snapshot_customer = next(c for c in snapshot.customers if c.customer_tag_uid == customer.tag.uid)
    assert snapshot_customer.balance_cents == round(initial_balance * 100)

    await assign_cash_register(cashier=cashier)
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    await order_service.book_topup(
        token=terminal_token,
        new_topup=NewTopUp(
            uuid=uuid4(),
            amount=20,
            payment_method=PaymentMethod.cash,
            customer_tag_uid=customer.tag.uid,
        ),
    )
    sale = sale_for(customer, sale_products)
    payload = OfflineImport(
        bookings=[
            OfflineBooking(snapshot_id=snapshot.id, sale=sale, sequence=1, recorded_at=datetime.now(timezone.utc))
        ]
    )
    first = await order_service.import_offline(token=terminal_token, payload=payload)
    assert first.results[0].status == OfflineBookingStatus.booked
    sale_total = first.results[0].sale.total_price

    expected_balance = initial_balance + Decimal(20) - Decimal(str(sale_total))
    assert Decimal(str(first.results[0].sale.new_balance)) == expected_balance
    assert (
        await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == expected_balance
    )
    assert next(c for c in snapshot.customers if c.customer_tag_uid == customer.tag.uid).balance_cents == round(
        initial_balance * 100
    )
    persisted_snapshot = await db_connection.fetchval(
        "select snapshot from terminal_offline_snapshot where id=$1", snapshot.id
    )
    persisted_customer = next(c for c in persisted_snapshot["customers"] if c["customer_tag_uid"] == customer.tag.uid)
    assert persisted_customer["balance_cents"] == round(initial_balance * 100)

    replay = await order_service.import_offline(token=terminal_token, payload=payload)
    assert replay.results[0].status == OfflineBookingStatus.already_booked
    assert (
        await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == expected_balance
    )


async def test_offline_invalid_record_does_not_abort_batch(
    prepared_offline, order_service, terminal_token, customer, sale_products, event_admin_token, event_node
):
    sale = sale_for(customer, sale_products)
    expired = OfflineBooking(
        snapshot_id=prepared_offline.id,
        sale=sale,
        sequence=1,
        recorded_at=prepared_offline.valid_until + timedelta(seconds=1),
    )
    valid = OfflineBooking(
        snapshot_id=prepared_offline.id,
        sale=sale_for(customer, sale_products),
        sequence=2,
        recorded_at=prepared_offline.server_time,
    )
    results = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[expired, valid]))
    assert results.results[0].status == OfflineBookingStatus.clarification_required
    assert results.results[1].status == OfflineBookingStatus.booked
    with pytest.raises(InvalidArgument, match="clarification"):
        await order_service.prepare_offline(token=terminal_token)


async def test_offline_limits_count_gross_returns_separately(prepared_offline, customer, sale_products):
    sale = sale_for(customer, sale_products, quantity=5)
    sale.buttons.append(Button(till_button_id=sale_products.deposit_button.id, quantity=-5))
    _, positive, negative = offline_positions(prepared_offline, sale)
    assert (positive, negative) == (2500, 1000)
    with pytest.raises(InvalidArgument, match="budget"):
        check_offline_budget(prepared_offline, sale, positive, negative, [])


async def test_offline_snapshot_accepts_single_variable_price_product(
    prepared_offline_with_free_price, free_price_product
):
    button = next(b for b in prepared_offline_with_free_price.buttons if b.id == free_price_product.button.id)
    assert len(button.products) == 1
    assert button.products[0].id == free_price_product.product.id
    assert button.products[0].fixed_price is False
    assert button.products[0].is_returnable is False
    assert all(b.id != free_price_product.mixed_button.id for b in prepared_offline_with_free_price.buttons)


async def test_offline_free_price_counts_gross_amount_and_allows_tips(
    prepared_offline_with_free_price, customer, free_price_product
):
    sale = free_price_sale(customer, free_price_product, price=12.34)
    positions, positive, negative = offline_positions(prepared_offline_with_free_price, sale)
    assert (positive, negative) == (1234, 0)
    assert len(positions) == 1
    assert positions[0].product.id == free_price_product.product.id
    assert positions[0].quantity == 1
    assert positions[0].product_price == 12.34


@pytest.mark.parametrize("price", [-0.01, 1.001, float("inf"), float("nan")])
async def test_offline_free_price_rejects_invalid_cents(
    prepared_offline_with_free_price, customer, free_price_product, price
):
    with pytest.raises(InvalidArgument):
        offline_positions(prepared_offline_with_free_price, free_price_sale(customer, free_price_product, price))


async def test_offline_free_price_rejects_fixed_product_price_override(prepared_offline, customer, sale_products):
    sale = sale_for(customer, sale_products)
    sale.buttons[0] = Button(till_button_id=sale_products.beer_button.id, price=1.23)
    with pytest.raises(InvalidArgument):
        offline_positions(prepared_offline, sale)


async def test_offline_free_price_rejects_quantity_without_amount(
    prepared_offline_with_free_price, customer, free_price_product
):
    sale = free_price_sale(customer, free_price_product, price=1.0)
    sale.buttons[0] = Button(till_button_id=free_price_product.button.id, quantity=1)
    with pytest.raises(InvalidArgument):
        offline_positions(prepared_offline_with_free_price, sale)


async def test_offline_free_price_rejects_mixed_product_button(
    prepared_offline_with_free_price, customer, free_price_product
):
    sale = NewSale(
        uuid=uuid4(),
        customer_tag_uid=customer.tag.uid,
        payment_method=PaymentMethod.tag,
        used_vouchers=0,
        buttons=[Button(till_button_id=free_price_product.mixed_button.id, price=3.00)],
    )
    with pytest.raises(InvalidArgument):
        offline_positions(prepared_offline_with_free_price, sale)


async def test_offline_free_price_import_preserves_amount_tax_and_distinct_prices(
    prepared_offline_with_free_price,
    order_service,
    terminal_token,
    customer,
    free_price_product,
    db_connection,
):
    snapshot = prepared_offline_with_free_price
    snapshot_product = next(p for b in snapshot.buttons for p in b.products if p.id == free_price_product.product.id)
    await db_connection.execute(
        "update tax_rate set rate=0.3,name='changed donation tax' where id=$1",
        free_price_product.product.tax_rate_id,
    )
    sale = free_price_sale(customer, free_price_product, price=2.50)
    sale.buttons.append(Button(till_button_id=free_price_product.button.id, price=4.00))
    booking = OfflineBooking(
        snapshot_id=snapshot.id,
        sale=sale,
        sequence=1,
        recorded_at=snapshot.server_time,
    )

    first = await order_service.import_offline(
        token=terminal_token,
        payload=OfflineImport(bookings=[booking]),
    )
    assert first.results[0].status == OfflineBookingStatus.booked
    assert first.results[0].sale.total_price == 6.50
    line_items = await db_connection.fetch(
        "select product_price,quantity,tax_rate,tax_name from line_item "
        "where order_id=$1 and product_id=$2 order by product_price",
        first.results[0].sale.id,
        free_price_product.product.id,
    )
    assert [(float(row["product_price"]), row["quantity"]) for row in line_items] == [(2.5, 1), (4.0, 1)]
    assert all(float(row["tax_rate"]) == snapshot_product.tax_rate for row in line_items)
    assert all(row["tax_name"] == snapshot_product.tax_name for row in line_items)

    replay = await order_service.import_offline(
        token=terminal_token,
        payload=OfflineImport(bookings=[booking]),
    )
    assert replay.results[0].status == OfflineBookingStatus.already_booked
    assert replay.results[0].sale.id == first.results[0].sale.id
    assert (
        await db_connection.fetchval(
            "select count(*) from line_item where order_id=$1 and product_id=$2",
            first.results[0].sale.id,
            free_price_product.product.id,
        )
        == 2
    )


async def test_offline_returns_never_replenish_estimated_balance(prepared_offline, customer, sale_products):
    sale = sale_for(customer, sale_products)
    uid = customer.tag.uid
    c = next(c for c in prepared_offline.customers if c.customer_tag_uid == uid)
    c.balance_cents = 500
    with pytest.raises(InvalidArgument, match="balance"):
        check_offline_budget(prepared_offline, sale, 500, 0, [(uid, 500, 0), (uid, 0, 500)])


async def test_offline_requires_explicit_zero_vouchers(prepared_offline, customer, sale_products):
    sale = sale_for(customer, sale_products)
    sale.used_vouchers = None
    with pytest.raises(InvalidArgument, match="vouchers"):
        offline_positions(prepared_offline, sale)


async def test_legacy_uuid_recovers_without_new_debit(
    order_service, terminal_token, customer, sale_products, cashier, login_supervised_user, db_connection
):
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    sale = sale_for(customer, sale_products)
    first = await order_service.book_sale(token=terminal_token, new_sale=sale)
    await db_connection.execute("delete from terminal_sale_journal where uuid=$1", sale.uuid)
    result = await order_service.book_sale(token=terminal_token, new_sale=sale)
    assert result.id == first.id
    assert result.new_balance == first.new_balance
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", sale.uuid) == 1


async def test_unknown_snapshot_durable_and_dismissible(
    prepared_offline, order_service, terminal_token, customer, sale_products, event_admin_token, event_node
):
    sale = sale_for(customer, sale_products)
    booking = OfflineBooking(snapshot_id=uuid4(), sale=sale, sequence=1, recorded_at=prepared_offline.server_time)
    result = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert result.results[0].status == OfflineBookingStatus.clarification_required
    status = await order_service.offline_booking_status(token=terminal_token, order_uuid=sale.uuid)
    assert status.status == OfflineBookingStatus.clarification_required
    report = await order_service.offline_report(token=event_admin_token, node_id=event_node.id)
    assert report[0].uuid == sale.uuid
    await order_service.dismiss_offline(token=event_admin_token, node_id=event_node.id, order_uuid=sale.uuid)
    status = await order_service.offline_booking_status(token=terminal_token, order_uuid=sale.uuid)
    assert status.status == OfflineBookingStatus.dismissed
    await order_service.prepare_offline(token=terminal_token)


async def test_historical_tax_name_and_rate_preserved(
    prepared_offline, order_service, terminal_token, customer, sale_products, db_connection
):
    old_rate = sale_products.beer_product.tax_rate
    await db_connection.execute(
        "update tax_rate set rate=0.3,name='changed tax' where id=$1", sale_products.beer_product.tax_rate_id
    )
    sale = sale_for(customer, sale_products)
    booking = OfflineBooking(
        snapshot_id=prepared_offline.id, sale=sale, sequence=1, recorded_at=prepared_offline.server_time
    )
    result = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert result.results[0].status == OfflineBookingStatus.booked
    persisted = await db_connection.fetchrow(
        "select tax_rate,tax_name from line_item where order_id=$1 and product_id=$2",
        result.results[0].sale.id,
        sale_products.beer_product.id,
    )
    assert float(persisted["tax_rate"]) == old_rate
    assert persisted["tax_name"] == sale_products.beer_product.tax_name


async def test_clarification_dismiss_unblocks_prepare(
    prepared_offline, order_service, terminal_token, customer, sale_products, event_admin_token, event_node
):
    sale = sale_for(customer, sale_products, quantity=5)
    booking = OfflineBooking(
        snapshot_id=prepared_offline.id, sale=sale, sequence=1, recorded_at=prepared_offline.server_time
    )
    result = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert result.results[0].status == OfflineBookingStatus.clarification_required
    await order_service.dismiss_offline(token=event_admin_token, node_id=event_node.id, order_uuid=sale.uuid)
    status = await order_service.offline_booking_status(token=terminal_token, order_uuid=sale.uuid)
    assert status.status == OfflineBookingStatus.dismissed
    assert (await order_service.prepare_offline(token=terminal_token)).id != prepared_offline.id


async def test_online_concurrent_same_uuid_posts_once(
    order_service, terminal_token, customer, sale_products, cashier, login_supervised_user, db_connection
):
    import asyncio

    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    sale = sale_for(customer, sale_products)
    results = await asyncio.gather(*(order_service.book_sale(token=terminal_token, new_sale=sale) for _ in range(2)))
    assert results[0] == results[1]
    assert await db_connection.fetchval("select count(*) from ordr where uuid=$1", sale.uuid) == 1


async def test_online_concurrent_distinct_sales_recheck_balance(
    order_service, terminal_token, customer, sale_products, cashier, login_supervised_user, db_connection
):
    import asyncio

    from stustapay.core.service.order.order import NotEnoughFundsException

    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    await db_connection.execute("update account set balance=7 where id=$1", customer.account_id)
    results = await asyncio.gather(
        *(order_service.book_sale(token=terminal_token, new_sale=sale_for(customer, sale_products)) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(isinstance(r, NotEnoughFundsException) for r in results) == 1
    assert await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == 2


async def test_revoked_snapshot_registration_becomes_clarification(
    prepared_offline, order_service, terminal_token, customer, sale_products, db_connection
):
    await db_connection.execute(
        "update terminal_offline_snapshot set session_uuid=$2 where id=$1", prepared_offline.id, uuid4()
    )
    booking = OfflineBooking(
        snapshot_id=prepared_offline.id,
        sale=sale_for(customer, sale_products),
        sequence=1,
        recorded_at=prepared_offline.server_time,
    )
    result = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert result.results[0].status == OfflineBookingStatus.clarification_required
    assert "registration" in result.results[0].message


async def test_online_journal_survives_terminal_deletion(
    order_service,
    terminal_service,
    terminal_token,
    terminal,
    customer,
    sale_products,
    cashier,
    login_supervised_user,
    event_admin_token,
    event_node,
    db_connection,
):
    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    sale = sale_for(customer, sale_products)
    booked = await order_service.book_sale(token=terminal_token, new_sale=sale)
    await terminal_service.logout_terminal(token=terminal_token)
    assert await terminal_service.delete_terminal(
        token=event_admin_token, node_id=event_node.id, terminal_id=terminal.id
    )
    assert (
        await db_connection.fetchval("select terminal_id from terminal_sale_journal where uuid=$1", sale.uuid)
        == terminal.id
    )
    assert await db_connection.fetchval("select id from ordr where uuid=$1", sale.uuid) == booked.id


async def test_offline_history_survives_terminal_deletion(
    prepared_offline,
    order_service,
    terminal_service,
    terminal,
    terminal_token,
    customer,
    sale_products,
    event_admin_token,
    event_node,
    db_connection,
):
    sale = sale_for(customer, sale_products)
    booking = OfflineBooking(
        snapshot_id=prepared_offline.id, sale=sale, sequence=1, recorded_at=prepared_offline.server_time
    )
    result = await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    assert result.results[0].status == OfflineBookingStatus.booked
    await terminal_service.logout_terminal(token=terminal_token)
    assert await terminal_service.delete_terminal(
        token=event_admin_token, node_id=event_node.id, terminal_id=terminal.id
    )
    report = await order_service.offline_report(token=event_admin_token, node_id=event_node.id)
    assert report[0].uuid == sale.uuid
    assert report[0].terminal_id == terminal.id
    assert report[0].order_id == result.results[0].sale.id
    assert (
        await db_connection.fetchval(
            "select terminal_id from terminal_offline_snapshot where id=$1", prepared_offline.id
        )
        == terminal.id
    )


async def test_rejection_history_survives_terminal_deletion(
    prepared_offline,
    order_service,
    terminal_service,
    terminal,
    terminal_token,
    customer,
    sale_products,
    event_admin_token,
    event_node,
):
    sale = sale_for(customer, sale_products)
    booking = OfflineBooking(snapshot_id=uuid4(), sale=sale, sequence=1, recorded_at=prepared_offline.server_time)
    await order_service.import_offline(token=terminal_token, payload=OfflineImport(bookings=[booking]))
    await terminal_service.logout_terminal(token=terminal_token)
    assert await terminal_service.delete_terminal(
        token=event_admin_token, node_id=event_node.id, terminal_id=terminal.id
    )
    report = await order_service.offline_report(token=event_admin_token, node_id=event_node.id)
    assert report[0].uuid == sale.uuid
    assert report[0].terminal_id == terminal.id
    await order_service.dismiss_offline(token=event_admin_token, node_id=event_node.id, order_uuid=sale.uuid)
    report = await order_service.offline_report(token=event_admin_token, node_id=event_node.id)
    assert report[0].status == OfflineBookingStatus.dismissed


async def test_distinct_terminals_serialize_customer_balance(
    order_service,
    terminal_service,
    terminal_token,
    create_terminal_token,
    customer,
    sale_products,
    till,
    cashier,
    login_supervised_user,
    db_connection,
):
    import asyncio

    from stustapay.core.service.order.order import NotEnoughFundsException

    await login_supervised_user(user_tag_uid=cashier.user_tag_uid, user_role_id=cashier.cashier_role.id)
    second_token = await create_terminal_token()
    config = await terminal_service.get_terminal_config(token=second_token)
    await db_connection.execute(
        "update till set active_profile_id=$1 where id=$2", till.active_profile_id, config.till.id
    )
    await db_connection.execute("update account set balance=7 where id=$1", customer.account_id)
    results = await asyncio.gather(
        *(
            order_service.book_sale(token=t, new_sale=sale_for(customer, sale_products))
            for t in (terminal_token, second_token)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(r, NotEnoughFundsException) for r in results) == 1
    assert await db_connection.fetchval("select balance from account where id=$1", customer.account_id) == 2
