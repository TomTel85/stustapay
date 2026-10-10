from sftkit.database import Connection

from .handler import TSESignatureRequest
from .kassenbeleg_v1 import Kassenbeleg_V1

PAYMENT_METHOD_TO_ZAHLUNGSART = {"cash": "Bar", "sumup": "Unbar", "tag": "Unbar", "sumup_online": "Unbar"}


async def make_signature_request(conn: Connection, order_id: int, till_id: str):
    """
    Collects all required information for signing the order,
    and passes the signing request to the TSE.
    """
    payment_method = await conn.fetchval("select payment_method from ordr where ordr.id=$1", order_id)
    if payment_method is None:
        raise RuntimeError(f"invalid order {order_id!r}")
    beleg = Kassenbeleg_V1()
    total = 0
    try:
        zahlungsart = PAYMENT_METHOD_TO_ZAHLUNGSART[payment_method]
    except KeyError as exc:
        raise RuntimeError(f"invalid payment_method {payment_method!r}") from exc

    for row in await conn.fetch("select total_price, tax_name from line_item where order_id = $1", order_id):
        beleg.add_line_item(row["total_price"], row["tax_name"])
        total += row["total_price"]
    # TODO: get currency from database config
    beleg.add_zahlung(total, zahlungsart=zahlungsart, waehrung="EUR")

    return TSESignatureRequest(
        order_id=order_id,
        till_id=till_id,
        process_type=beleg.get_process_type(),
        process_data=beleg.get_process_data(),
    )
