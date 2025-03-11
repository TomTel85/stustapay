import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, computed_field

from stustapay.core.schema.order import OrderType
from stustapay.core.schema.product import Product, ProductRestriction
from stustapay.core.schema.user import format_user_tag_uid


class AccountType(enum.Enum):
    private = "private"
    sale_exit = "sale_exit"
    cash_entry = "cash_entry"
    cash_exit = "cash_exit"
    cash_topup_source = "cash_topup_source"
    cash_imbalance = "cash_imbalance"
    cash_vault = "cash_vault"
    sumup_entry = "sumup_entry"
    sumup_online_entry = "sumup_online_entry"
    transport = "transport"
    # cashier = "cashier"  # LEGACY, not used anymore, kept for reference
    voucher_create = "voucher_create"
    donation_exit = "donation_exit"
    sepa_exit = "sepa_exit"
    cash_register = "cash_register"


def get_source_account(order_type: OrderType, customer_account: int):
    """
    return the transaction source account, depending on the order type or sold product
    """
    if order_type == OrderType.sale:
        return customer_account
    raise NotImplementedError()


def get_target_account(order_type: OrderType, product: Product, sale_exit_account_id: int):
    """
    return the transaction target account, depending on the order type or sold product
    """
    if order_type == OrderType.sale:
        if product.target_account_id is not None:
            return product.target_account_id
        return sale_exit_account_id
    raise NotImplementedError()


class UserTagAccountAssociation(BaseModel):
    account_id: int
    mapping_was_valid_until: datetime


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

    @computed_field  # type: ignore[misc]
    @property
    def uid_hex(self) -> Optional[str]:
        return format_user_tag_uid(self.uid)


class UserTagHistoryEntry(BaseModel):
    user_tag_id: int
    user_tag_pin: str
    user_tag_uid: Optional[int]

    account_id: int
    comment: Optional[str] = None
    mapping_was_valid_until: datetime

    @computed_field  # type: ignore[misc]
    @property
    def user_tag_uid_hex(self) -> Optional[str]:
        return format_user_tag_uid(self.user_tag_uid)


class Account(BaseModel):
    node_id: int
    id: int
    type: AccountType
    name: Optional[str]
    comment: Optional[str]
    balance: float
    vouchers: int

    # metadata relevant to a tag
    user_tag_id: Optional[int]
    user_tag_uid: Optional[int]
    user_tag_comment: Optional[str] = None
    restriction: Optional[ProductRestriction]
    is_vip: bool = False
    vip_max_balance: Optional[float] = None

    tag_history: list[UserTagHistoryEntry]

    @computed_field  # type: ignore[misc]
    @property
    def user_tag_uid_hex(self) -> Optional[str]:
        return format_user_tag_uid(self.user_tag_uid)
