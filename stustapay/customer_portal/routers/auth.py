from fastapi import APIRouter, status, Request
from pydantic import BaseModel

from stustapay.core.http.auth_customer import CurrentAuthToken
from stustapay.core.http.context import ContextCustomerService
from stustapay.core.schema.customer import Customer
from stustapay.core.service.common.error import AccessDenied

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={404: {"description": "Not found"}},
)


class LoginPayload(BaseModel):
    username: str
    pin: str


class LoginResponse(BaseModel):
    customer: Customer
    access_token: str
    grant_type: str = "bearer"


@router.get("/login/qr", summary="customer login via QR code")
async def login_with_qr(username: str, pin: str, customer_service: ContextCustomerService, request: Request):
    try:
        user_tag_uid = int(username, 16)
    except Exception as e:  # pylint: disable=broad-except
        raise AccessDenied("Invalid user tag") from e
    
    # Get node_id from config
    base_url = str(request.base_url)
    config = await customer_service.get_api_config(base_url=base_url)
    
    # Process the QR code login
    response = await customer_service.login_customer(uid=user_tag_uid, pin=pin, node_id=config.node_id)
    return {"customer": response.customer, "access_token": response.token, "grant_type": "bearer"}


@router.post("/login", summary="customer login with wristband hardware tag and pin", response_model=LoginResponse)
async def login(
    payload: LoginPayload,
    customer_service: ContextCustomerService,
    request: Request,
):
    try:
        user_tag_uid = int(payload.username, 16)
    except Exception as e:  # pylint: disable=broad-except
        raise AccessDenied("Invalid user tag") from e
    
    # Get node_id from config
    base_url = str(request.base_url)
    config = await customer_service.get_api_config(base_url=base_url)
    
    response = await customer_service.login_customer(uid=user_tag_uid, pin=payload.pin, node_id=config.node_id)
    return {"customer": response.customer, "access_token": response.token, "grant_type": "bearer"}


@router.post(
    "/logout",
    summary="sign out of the current session",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    token: CurrentAuthToken,
    customer_service: ContextCustomerService,
):
    await customer_service.logout_customer(token=token)
