from fastapi import APIRouter
from pydantic import BaseModel
from fastapi import HTTPException

from stustapay.core.http.auth_user import CurrentAuthToken
from stustapay.core.http.context import ContextCashierService, ContextOrderService, ContextTillService
from stustapay.core.http.normalize_data import NormalizedList, normalize_list
from stustapay.core.schema.cashier import CashierShift
from stustapay.core.schema.order import Transaction
from stustapay.core.schema.till import CashRegister, NewCashRegister

router = APIRouter(
    prefix="/till-registers",
    tags=["till-registers"],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=NormalizedList[CashRegister, int])
async def list_cash_registers_admin(token: CurrentAuthToken, till_service: ContextTillService, node_id: int):
    return normalize_list(await till_service.register.list_cash_registers_admin(token=token, node_id=node_id))


@router.get("/{register_id}", response_model=CashRegister)
async def get_cash_register_admin(
    token: CurrentAuthToken, till_service: ContextTillService, node_id: int, register_id: int
):
    return await till_service.register.get_cash_register_admin(token=token, node_id=node_id, register_id=register_id)


@router.get("/{register_id}/cashier-shifts", response_model=NormalizedList[CashierShift, int])
async def get_cashier_shifts_for_register(
    token: CurrentAuthToken, register_id: int, cashier_service: ContextCashierService, node_id: int
):
    return normalize_list(
        await cashier_service.get_cashier_shifts_for_cash_register(
            token=token, cash_register_id=register_id, node_id=node_id
        )
    )


@router.get("/{register_id}/transactions", response_model=NormalizedList[Transaction, int])
async def list_transactions(
    token: CurrentAuthToken,
    order_service: ContextOrderService,
    node_id: int,
    register_id: int,
):
    return normalize_list(
        await order_service.list_transactions_by_cash_register(
            token=token, cash_register_id=register_id, node_id=node_id
        )
    )


@router.post("", response_model=CashRegister)
async def create_register(
    register: NewCashRegister, token: CurrentAuthToken, till_service: ContextTillService, node_id: int
):
    return await till_service.register.create_cash_register(token=token, new_register=register, node_id=node_id)


class TransferRegisterPayload(BaseModel):
    source_cashier_id: int
    target_cashier_id: int


@router.post("/transfer-register")
async def transfer_register(
    token: CurrentAuthToken,
    payload: TransferRegisterPayload,
    till_service: ContextTillService,
    node_id: int,
):
    return await till_service.register.transfer_cash_register_admin(
        token=token,
        source_cashier_id=payload.source_cashier_id,
        target_cashier_id=payload.target_cashier_id,
        node_id=node_id,
    )


class AssignRegisterPayload(BaseModel):
    cashier_id: int
    cash_register_id: int


@router.post("/assign-register")
async def assign_register(
    token: CurrentAuthToken,
    payload: AssignRegisterPayload,
    till_service: ContextTillService,
    node_id: int,
):
    return await till_service.register.assign_cash_register_admin(
        token=token,
        cashier_id=payload.cashier_id,
        cash_register_id=payload.cash_register_id,
        node_id=node_id,
    )


class ModifyRegisterBalancePayload(BaseModel):
    cashier_id: int
    amount: float


@router.post("/modify-balance")
async def modify_register_balance(
    token: CurrentAuthToken,
    payload: ModifyRegisterBalancePayload,
    till_service: ContextTillService,
    cashier_service: ContextCashierService,
    node_id: int,
):
    # Get the cashier's user tag UID which is required by modify_cashier_account_balance
    cashier = await cashier_service.get_cashier(token=token, node_id=node_id, cashier_id=payload.cashier_id)
    if not cashier.user_tag_uid:
        raise HTTPException(status_code=400, detail="Cashier does not have a user tag")
    
    return await till_service.register.modify_cashier_account_balance_admin(
        token=token,
        cashier_id=payload.cashier_id,
        cashier_tag_uid=cashier.user_tag_uid,
        amount=payload.amount,
        node_id=node_id,
    )


@router.post("/{register_id}")
async def update_register(
    register_id: int,
    register: NewCashRegister,
    token: CurrentAuthToken,
    till_service: ContextTillService,
    node_id: int,
):
    return await till_service.register.update_cash_register(
        token=token, register_id=register_id, register=register, node_id=node_id
    )


@router.delete("/{register_id}")
async def delete_register(register_id: int, token: CurrentAuthToken, till_service: ContextTillService, node_id: int):
    return await till_service.register.delete_cash_register(token=token, register_id=register_id, node_id=node_id)
