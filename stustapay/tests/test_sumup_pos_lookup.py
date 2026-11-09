import uuid
from unittest.mock import AsyncMock

import pytest

from stustapay.payment.sumup.api import SumUpApi, SumUpError


@pytest.mark.asyncio
async def test_find_pos_transaction(monkeypatch):
    order_id = uuid.uuid4()
    api = SumUpApi("key", "merchant")
    get = AsyncMock(
        return_value={
            "id": "transaction",
            "transaction_code": "code",
            "foreign_transaction_id": str(order_id),
            "amount": 12.5,
            "currency": "EUR",
            "status": "SUCCESSFUL",
            "timestamp": "2026-01-01T00:00:00Z",
        }
    )
    monkeypatch.setattr(api, "_get", get)
    transaction = await api.find_pos_transaction(order_id)
    assert transaction is not None
    assert transaction.status == "SUCCESSFUL"
    get.assert_awaited_once_with(
        "https://api.sumup.com/v2.1/merchants/merchant/transactions",
        query={"foreign_transaction_id": str(order_id)},
    )
    get.side_effect = SumUpError("not found", status=404)
    assert await api.find_pos_transaction(order_id) is None
    get.side_effect = SumUpError("unavailable", status=503)
    with pytest.raises(SumUpError):
        await api.find_pos_transaction(order_id)
    get.side_effect = None
    get.return_value["foreign_transaction_id"] = str(uuid.uuid4())
    with pytest.raises(SumUpError):
        await api.find_pos_transaction(order_id)


@pytest.mark.asyncio
async def test_get_preserves_http_status(monkeypatch):
    class Response:
        ok = False
        status = 404

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def text(self):
            return "not found"

        async def json(self, **_kwargs):
            return {"message": "not found"}

    class Session:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("stustapay.payment.sumup.api.aiohttp.ClientSession", Session)
    assert await SumUpApi("key", "merchant").find_pos_transaction(uuid.uuid4()) is None
