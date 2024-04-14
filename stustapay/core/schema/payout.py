from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, computed_field

from stustapay.core.schema.user import format_user_tag_uid


class NewPayoutRun(BaseModel):
    max_payout_sum: Decimal


class PayoutRun(BaseModel):
    id: int
    created_by: str
    created_at: datetime


class PendingPayoutDetail(BaseModel):
    total_payout_amount: Decimal
    total_donation_amount: Decimal
    n_payouts: int


class PayoutRunWithStats(PayoutRun):
    total_donation_amount: Decimal
    total_payout_amount: Decimal
    n_payouts: int


class Payout(BaseModel):
    customer_account_id: int
    iban: str
    account_name: str
    email: str
    user_tag_uid: int

    @computed_field
    def user_tag_uid_hex(self) -> str:
        return format_user_tag_uid(self.user_tag_uid)  # type: ignore

    balance: Decimal
    payout_run_id: int
