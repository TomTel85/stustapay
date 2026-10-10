from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class NewFiskalySite(BaseModel):
    customer_node_id: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=100)
    operator_name: str = Field(min_length=3, max_length=100)
    address_line1: str = Field(min_length=1, max_length=200)
    zip: str = Field(min_length=1, max_length=20)
    town: str = Field(min_length=1, max_length=100)
    country_code: Literal["DEU"] = "DEU"
    vat_id: str | None = Field(default=None, max_length=50)

    @field_validator("name", "operator_name", "address_line1", "zip", "town", mode="before")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Fiskaly site data must be text")
        value = value.strip()
        if not value:
            raise ValueError("Fiskaly site data must not be blank")
        return value


class FiskalySite(NewFiskalySite):
    id: int
    organization_id: UUID | None = None


class NewFiskalyProvisioningJob(BaseModel):
    site_id: int
    event_node_id: int
    environment: Literal["TEST", "LIVE"] = "TEST"


class FiskalyProvisioningJob(NewFiskalyProvisioningJob):
    id: int
    status: Literal["queued", "running", "ready", "retry_wait", "action_required", "failed"]
    step: str
    last_error: str | None = None
    tse_id: int | None = None
    attempts: int
