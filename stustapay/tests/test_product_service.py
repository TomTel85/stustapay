# pylint: disable=attribute-defined-outside-init,unexpected-keyword-arg,missing-kwoa
from decimal import Decimal

import pytest
from asyncpg import CheckViolationError, RaiseError
from pydantic import ValidationError
from sftkit.database import Connection
from sftkit.error import AccessDenied

from stustapay.core.schema.product import NewProduct
from stustapay.core.schema.tax_rate import TaxRate
from stustapay.core.schema.till import NewTillButton
from stustapay.core.schema.tree import NewNode, Node
from stustapay.core.service.product import ProductService
from stustapay.core.service.till.till import TillService

from ..core.service.tree.service import create_node
from .conftest import Cashier


@pytest.mark.parametrize("price,expected", [(1.005, 1.01), (2.345, 2.35), (-1.005, -1.01), (2.3, 2.3), (None, None)])
def test_product_price_rounds_decimal_half_cents(price, expected):
    assert NewProduct(name="Rounded", price=price, tax_rate_id=1).price == expected


@pytest.mark.parametrize("price", [float("nan"), float("inf"), float("-inf")])
def test_product_price_rejects_nonfinite_values(price):
    with pytest.raises(ValidationError, match="finite"):
        NewProduct(name="Invalid", price=price, tax_rate_id=1)


async def test_product_prices_are_normalized_for_every_database_writer(db_connection, event_node, tax_rate_none):
    product_id = await db_connection.fetchval(
        "insert into product(node_id,name,type,price,tax_rate_id) values($1,'Precision test','user_defined',$2,$3) "
        "returning id",
        event_node.id,
        Decimal("1.005"),
        tax_rate_none.id,
    )
    assert await db_connection.fetchval("select price from product where id=$1", product_id) == Decimal("1.01")
    await db_connection.execute("update product set price=$2 where id=$1", product_id, Decimal("2.34567"))
    assert await db_connection.fetchval("select price from product where id=$1", product_id) == Decimal("2.35")
    for value in ("NaN", "Infinity", "-Infinity"):
        async with db_connection.transaction():
            with pytest.raises(CheckViolationError):
                # Roll the failed statement back without losing the surrounding test data.
                async with db_connection.transaction():
                    await db_connection.execute("update product set price=$2 where id=$1", product_id, Decimal(value))
    await db_connection.execute("update product set fixed_price=false, price=null where id=$1", product_id)
    assert await db_connection.fetchval("select price from product where id=$1", product_id) is None


async def test_basic_product_workflow(
    product_service: ProductService,
    event_node: Node,
    tax_rate_ust: TaxRate,
    tax_rate_none: TaxRate,
    event_admin_token: str,
    cashier: Cashier,
):
    product = await product_service.create_product(
        token=event_admin_token,
        node_id=event_node.id,
        product=NewProduct(name="Test Product", price=3, tax_rate_id=tax_rate_ust.id),
    )

    assert product.name == "Test Product"
    assert product.is_donation is False

    with pytest.raises(AccessDenied):
        await product_service.create_product(
            token=cashier.token,
            node_id=event_node.id,
            product=NewProduct(name="Test Product", price=3, tax_rate_id=tax_rate_ust.id),
        )

    updated_product = await product_service.update_product(
        token=event_admin_token,
        product_id=product.id,
        node_id=event_node.id,
        product=NewProduct(name="Updated Test Product", price=4, tax_rate_id=tax_rate_none.id, is_donation=True),
    )
    assert updated_product.name == "Updated Test Product"
    assert updated_product.price == 4
    assert updated_product.tax_name == tax_rate_none.name
    assert updated_product.is_donation is True

    products = await product_service.list_products(token=event_admin_token, node_id=event_node.id)
    assert len(list(filter(lambda p: p.name == "Updated Test Product", products))) == 1

    with pytest.raises(AccessDenied):
        await product_service.delete_product(token=cashier.token, node_id=event_node.id, product_id=product.id)

    deleted = await product_service.delete_product(
        token=event_admin_token, node_id=event_node.id, product_id=product.id
    )
    assert deleted


async def test_product_name_is_unique_in_tree(
    product_service: ProductService,
    db_connection: Connection,
    event_node: Node,
    tax_rate_none: TaxRate,
    event_admin_token: str,
):
    sub_node = await create_node(
        conn=db_connection,
        parent_id=event_node.id,
        new_node=NewNode(
            name="sub node", description="", forbidden_objects_at_node=[], forbidden_objects_in_subtree=[]
        ),
    )
    sub_sub_node = await create_node(
        conn=db_connection,
        parent_id=sub_node.id,
        new_node=NewNode(
            name="sub sub node", description="", forbidden_objects_at_node=[], forbidden_objects_in_subtree=[]
        ),
    )
    product = NewProduct(name="Test Product", price=3, tax_rate_id=tax_rate_none.id)
    await product_service.create_product(
        token=event_admin_token,
        node_id=sub_node.id,
        product=product,
    )

    with pytest.raises(RaiseError):
        # will not allow a duplicate name on the same node
        await product_service.create_product(
            token=event_admin_token,
            node_id=sub_node.id,
            product=product,
        )
    with pytest.raises(RaiseError):
        # will not allow a duplicate name in a sub node
        await product_service.create_product(
            token=event_admin_token,
            node_id=event_node.id,
            product=product,
        )
    with pytest.raises(RaiseError):
        # will not allow a duplicate name in a parent node
        await product_service.create_product(
            token=event_admin_token,
            node_id=sub_sub_node.id,
            product=product,
        )


async def test_update_product_assigned_to_button(
    product_service: ProductService,
    till_service: TillService,
    event_node: Node,
    tax_rate_ust: TaxRate,
    tax_rate_none: TaxRate,
    event_admin_token: str,
):
    product = await product_service.create_product(
        token=event_admin_token,
        node_id=event_node.id,
        product=NewProduct(name="Button Product", price=3, tax_rate_id=tax_rate_ust.id),
    )

    await till_service.layout.create_button(
        token=event_admin_token,
        node_id=event_node.id,
        button=NewTillButton(name="Button Product", product_ids=[product.id]),
    )

    updated_product = await product_service.update_product(
        token=event_admin_token,
        node_id=event_node.id,
        product_id=product.id,
        product=NewProduct(name="Button Product Updated", price=4, tax_rate_id=tax_rate_none.id),
    )

    assert updated_product.name == "Button Product Updated"
    assert updated_product.price == 4
    assert updated_product.tax_rate_id == tax_rate_none.id
