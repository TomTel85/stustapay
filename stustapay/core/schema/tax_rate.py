from pydantic import BaseModel
from decimal import Decimal

TAX_NONE = "none"


class NewTaxRate(BaseModel):
    name: str
    rate: Decimal
    description: str


class TaxRate(NewTaxRate):
    id: int
    node_id: int
