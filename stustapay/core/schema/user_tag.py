from typing import Optional

from pydantic import BaseModel
from typing import Optional

from stustapay.core.schema.account import UserTagAccountAssociation
from stustapay.core.schema.product import ProductRestriction


def format_user_tag_uid(uid: Optional[int]) -> Optional[str]:
    if uid is None:
        return None

    return hex(uid)[2:].upper()


class UserTag(BaseModel):
    uid: int


class UserTagScan(BaseModel):
    """a scanned tag before ticket sale"""

    tag_uid: int
    tag_pin: str

    # requested custom top up amount
    top_up_amount: float = 0.0
    # ticket_voucher token via qr code
    voucher_token: Optional[str] = None


class NewUserTagSecret(BaseModel):
    key0: str
    key1: str
    description: str


class UserTagSecret(NewUserTagSecret):
    id: int
    node_id: int


class NewUserTag(BaseModel):
    pin: str
    restriction: ProductRestriction | None = None
    secret_id: int
    uid: Optional[int] = None
    is_vip: bool = False
    comment: Optional[str] = None


class UserTagDetail(BaseModel):
    id: int
    pin: str
    uid: Optional[int]
    node_id: int

    comment: Optional[str] = None
    account_id: Optional[int] = None
    user_id: Optional[int] = None
    is_vip: bool = False

    account_history: list[UserTagAccountAssociation]
