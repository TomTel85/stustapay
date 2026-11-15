from fastapi import APIRouter

from stustapay.core.http.auth_user import CurrentAuthToken
from stustapay.core.http.context import ContextFiskalyService
from stustapay.core.schema.fiskaly import (
    FiskalyProvisioningJob,
    FiskalySite,
    NewFiskalyProvisioningJob,
    NewFiskalySite,
)

router = APIRouter(prefix="/fiskaly", tags=["fiskaly"])


@router.get("/sites/", response_model=list[FiskalySite])
async def list_sites(token: CurrentAuthToken, service: ContextFiskalyService, node_id: int):
    return await service.list_sites(token=token, node_id=node_id)


@router.post("/sites/", response_model=FiskalySite)
async def create_site(token: CurrentAuthToken, service: ContextFiskalyService, node_id: int, site: NewFiskalySite):
    return await service.create_site(token=token, node_id=node_id, site=site)


@router.get("/sites/{site_id}/status", response_model=list[FiskalyProvisioningJob])
async def site_status(token: CurrentAuthToken, service: ContextFiskalyService, node_id: int, site_id: int):
    return await service.site_status(token=token, node_id=node_id, site_id=site_id)


@router.post("/provisioning/", response_model=FiskalyProvisioningJob, status_code=202)
async def start_provisioning(
    token: CurrentAuthToken,
    service: ContextFiskalyService,
    node_id: int,
    request: NewFiskalyProvisioningJob,
):
    return await service.start_provisioning(token=token, node_id=node_id, request=request)


@router.post("/provisioning/{job_id}/retry", response_model=FiskalyProvisioningJob, status_code=202)
async def retry_provisioning(token: CurrentAuthToken, service: ContextFiskalyService, node_id: int, job_id: int):
    return await service.retry_provisioning(token=token, node_id=node_id, job_id=job_id)


@router.patch("/provisioning/{job_id}/paused", response_model=FiskalyProvisioningJob)
async def set_fiskaly_provisioning_paused(
    token: CurrentAuthToken, service: ContextFiskalyService, node_id: int, job_id: int, paused: bool
):
    return await service.set_paused(token=token, node_id=node_id, job_id=job_id, paused=paused)
