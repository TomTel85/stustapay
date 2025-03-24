from pydantic import BaseModel
from typing import Optional

from stustapay.core.schema.account import UserTagAccountAssociation
from stustapay.core.schema.product import ProductRestriction


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
