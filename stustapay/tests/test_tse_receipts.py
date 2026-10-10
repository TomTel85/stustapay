import pytest
from sftkit.database import Connection

from stustapay.bon.bon import OrderWithTse, fetch_order, gen_dummy_order
from stustapay.core.schema.order import OrderType, PaymentMethod
from stustapay.core.schema.till import Till
from stustapay.core.schema.user import User
from stustapay.core.service.order.booking import book_order
from stustapay.core.service.tree.common import fetch_restricted_event_settings_for_node
from stustapay.dsfinvk.generator import Generator


def _done_order_with_tse() -> OrderWithTse:
    order_data = gen_dummy_order(node_id=1).model_dump(exclude={"signature_status", "tse_qr_code_text"})
    order_data.update(
        signature_status="done",
        transaction_process_type="Kassenbeleg-V1",
        transaction_process_data="Beleg^10.00_0.00_0.00_0.00_0.00^10.00:Bar",
        tse_transaction="transaction-1",
        tse_signaturenr="42",
        tse_start="2026-10-10T12:00:00.000Z",
        tse_end="2026-10-10T12:00:01.000Z",
        tse_hashalgo="ecdsa-plain-SHA384",
        tse_time_format="unixTime",
        tse_signature="signature-data",
        tse_public_key="public-key-data",
    )
    return OrderWithTse(**order_data)


def test_done_receipt_has_tse_qr_code_text():
    order = _done_order_with_tse()

    assert order.tse_qr_code_text == (
        "V0;0;Kassenbeleg-V1;Beleg^10.00_0.00_0.00_0.00_0.00^10.00:Bar;transaction-1;42;"
        "2026-10-10T12:00:00.000Z;2026-10-10T12:00:01.000Z;ecdsa-plain-SHA384;unixTime;"
        "signature-data;public-key-data"
    )


@pytest.mark.parametrize("status", ["new", "pending", "failure"])
def test_unsigned_receipt_has_no_tse_qr_code_text(status: str):
    order = _done_order_with_tse().model_copy(update={"signature_status": status})

    assert order.tse_qr_code_text is None


@pytest.mark.parametrize(
    "field",
    [
        "till_id",
        "transaction_process_type",
        "transaction_process_data",
        "tse_transaction",
        "tse_signaturenr",
        "tse_start",
        "tse_end",
        "tse_hashalgo",
        "tse_time_format",
        "tse_signature",
        "tse_public_key",
    ],
)
def test_done_receipt_with_incomplete_tse_data_has_no_qr_code_text(field: str):
    order = _done_order_with_tse().model_copy(update={field: None})

    assert order.tse_qr_code_text is None


async def test_fetch_order_includes_order_without_tse_assignment(db_connection: Connection, cashier: User, till: Till):
    booked = await book_order(
        conn=db_connection,
        order_type=OrderType.sale,
        payment_method=PaymentMethod.tag,
        cashier_id=cashier.id,
        till_id=till.id,
        line_items=[],
        bookings={},
    )

    order = await fetch_order(conn=db_connection, order_id=booked.id)

    assert order is not None
    assert order.signature_status == "new"
    assert order.result_message is None
    assert order.tse_qr_code_text is None


async def test_dsfinvk_exports_settled_failure_without_tse_assignment(
    config, db_connection: Connection, event_node, cashier: User, till: Till
):
    booked = await book_order(
        conn=db_connection,
        order_type=OrderType.sale,
        payment_method=PaymentMethod.tag,
        cashier_id=cashier.id,
        till_id=till.id,
        line_items=[],
        bookings={},
    )
    failure_message = "TSE signing unavailable"
    await db_connection.execute(
        "update tse_signature set signature_status = 'failure', result_message = $2 where id = $1",
        booked.id,
        failure_message,
    )
    settings = await fetch_restricted_event_settings_for_node(conn=db_connection, node_id=event_node.id)
    generator = Generator(config, event_node.id, "unused.zip", "unused.xml", "unused.dtd", False)

    await generator.einzelaufzeichnungsmodul(db_connection, till.z_nr, booked.booked_at, till.id, settings)

    bon_rows = generator.c.records["transactions.csv"]
    tse_rows = generator.c.records["transactions_tse.csv"]
    assert len(bon_rows) == 1
    assert bon_rows[0].data["BON_ID"] == booked.id
    assert len(tse_rows) == 1
    assert tse_rows[0].data["BON_ID"] == booked.id
    assert tse_rows[0].data["TSE_TA_FEHLER"] == f"TSE Fehler: {failure_message}"
    assert tse_rows[0].data["TSE_ID"] is None
