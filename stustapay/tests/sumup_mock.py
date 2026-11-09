import uuid
from datetime import datetime

from stustapay.payment.sumup.api import SumUpCheckout, SumUpCheckoutStatus, SumUpTransactionDetail


class MockSumUpApi:
    amount: float = 0

    def __init__(self, api_key: str, merchant_code: str):
        del api_key
        self.merchant_code = merchant_code

    async def find_checkout(self, order_uuid: uuid.UUID) -> SumUpCheckout | None:
        return SumUpCheckout(
            amount=self.amount,
            checkout_reference=order_uuid,
            currency="EUR",
            description="",
            id=str(uuid.uuid4()),
            merchant_code=self.merchant_code,
            status=SumUpCheckoutStatus.PAID,
            date=datetime.now(),
            redirect_url="http://localhost:4300/test",
        )

    @classmethod
    def mock_amount(cls, amount: float):
        cls.amount = amount

    async def find_pos_transaction(self, order_uuid: uuid.UUID) -> SumUpTransactionDetail | None:
        return pos_transaction_from_checkout(await self.find_checkout(order_uuid))


def pos_transaction_from_checkout(checkout: SumUpCheckout | None) -> SumUpTransactionDetail | None:
    if checkout is None:
        return None
    return SumUpTransactionDetail(
        id=checkout.id,
        amount=checkout.amount,
        currency=checkout.currency,
        timestamp=checkout.date,
        status="SUCCESSFUL" if checkout.status == SumUpCheckoutStatus.PAID else checkout.status.value,
        transaction_code="TEST",
        foreign_transaction_id=str(checkout.checkout_reference),
    )
