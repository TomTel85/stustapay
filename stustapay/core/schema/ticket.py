from pydantic import BaseModel

from stustapay.core.schema.product import ProductRestriction

from decimal import Decimal
class NewTicket(BaseModel):
    name: str
    price: Decimal
    tax_rate_id: int
    restrictions: list[ProductRestriction]
    is_locked: bool
    initial_top_up_amount: Decimal


class Ticket(NewTicket):
    node_id: int
    id: int

    tax_name: str
    tax_rate: Decimal
    total_price: Decimal
