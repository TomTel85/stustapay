from typing import Literal

from pydantic import BaseModel, Field

MfaError = Literal["invalid_credentials", "invalid_code", "rate_limited", "invalid_state"]


class MfaStatus(BaseModel):
    enabled: bool
    recovery_codes_remaining: int


class MfaUpdate(BaseModel):
    action: Literal["setup", "enable", "disable", "regenerate"]
    password: str = Field(max_length=1024)
    code: str = Field(default="", max_length=128)


class MfaResult(BaseModel):
    success: bool
    error: MfaError | None = None
    secret: str | None = None
    provisioning_uri: str | None = None
    recovery_codes: list[str] | None = None
