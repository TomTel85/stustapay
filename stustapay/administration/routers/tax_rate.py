from typing import Optional

from fastapi import APIRouter, HTTPException, status

from stustapay.core.http.auth_user import CurrentAuthToken
from stustapay.core.http.context import ContextTaxRateService
from stustapay.core.http.normalize_data import NormalizedList, normalize_list
from stustapay.core.schema.tax_rate import NewTaxRate, TaxRate

router = APIRouter(
    prefix="/tax-rates",
    tags=["tax-rates"],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=NormalizedList[TaxRate, int])
async def list_tax_rates(token: CurrentAuthToken, tax_service: ContextTaxRateService, node_id: Optional[int] = None):
    return normalize_list(await tax_service.list_tax_rates(token=token, node_id=node_id))


@router.post("", response_model=TaxRate)
async def create_tax_rate(
    tax_rate: NewTaxRate, token: CurrentAuthToken, tax_service: ContextTaxRateService, node_id: Optional[int] = None
):
    return await tax_service.create_tax_rate(token=token, tax_rate=tax_rate, node_id=node_id)


@router.get("/{tax_rate_id}", response_model=TaxRate)
async def get_tax_rate(
    tax_rate_id: int, token: CurrentAuthToken, tax_service: ContextTaxRateService, node_id: Optional[int] = None
):
    tax_rate = await tax_service.get_tax_rate(token=token, tax_rate_id=tax_rate_id, node_id=node_id)
    if tax_rate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return tax_rate


@router.post("/{tax_rate_id}", response_model=TaxRate)
async def update_tax_rate(
    tax_rate_id: int,
    tax_rate: NewTaxRate,
    token: CurrentAuthToken,
    tax_service: ContextTaxRateService,
    node_id: Optional[int] = None,
):
    return await tax_service.update_tax_rate(token=token, tax_rate_id=tax_rate_id, tax_rate=tax_rate, node_id=node_id)


@router.delete("/{tax_rate_id}")
async def delete_tax_rate(
    tax_rate_id: int, token: CurrentAuthToken, tax_service: ContextTaxRateService, node_id: Optional[int] = None
):
    deleted = await tax_service.delete_tax_rate(token=token, tax_rate_id=tax_rate_id, node_id=node_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
