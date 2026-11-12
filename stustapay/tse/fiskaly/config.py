from pathlib import Path
from typing import Literal
from uuid import UUID

from cryptography.fernet import Fernet
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

LIVE_UNAVAILABLE = "Fiskaly LIVE requires signing at the start and end of the fiscal operation"


class FiskalyManagementCredentials(BaseModel):
    environment: Literal["TEST", "LIVE"] = "TEST"
    group_id: UUID
    api_key: SecretStr
    api_secret: SecretStr
    request_timeout: float = Field(default=30, gt=0, le=60)
    max_concurrency: int = Field(default=2, ge=1, le=8)


class FiskalyManagementSettings(BaseModel):
    enabled: bool = False
    secret_key: SecretStr | None = None
    puk_directory: Path | None = None
    environments: dict[Literal["TEST", "LIVE"], FiskalyManagementCredentials] = Field(default_factory=dict)
    max_active_tses: int = Field(default=16, ge=1, le=64)

    @model_validator(mode="after")
    def validate_management(self):
        for environment, credentials in self.environments.items():  # pylint: disable=no-member
            if credentials.environment != environment:
                raise ValueError("Fiskaly management credential environment must match its configuration key")
            if (
                not credentials.api_key.get_secret_value().strip()
                or not credentials.api_secret.get_secret_value().strip()
            ):
                raise ValueError("Fiskaly management credentials must not be empty")
        if self.enabled:
            if not self.environments or self.secret_key is None:
                raise ValueError("Fiskaly management requires credentials and a dedicated encryption key")
            try:
                Fernet(self.secret_key.get_secret_value().encode())
            except (ValueError, TypeError):
                raise ValueError("Fiskaly management encryption key must be a valid Fernet key") from None
            if self.puk_directory is None or not self.puk_directory.is_absolute():
                raise ValueError("Fiskaly management requires an absolute private PUK directory")
        return self


class FiskalyConfig(BaseModel):
    """Configuration for existing fiscal resources or opt-in automatic provisioning.

    Credentials are supplied by the caller's secure configuration source. They
    must not be exposed through administration schemas or logged via model_dump.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr
    api_secret: SecretStr
    organization_id: UUID | None = None
    customer_node_id: int | None = Field(default=None, ge=1)
    tss_id: UUID | None = None
    environment: Literal["TEST", "LIVE"] = "TEST"
    request_timeout: float = Field(default=5, gt=0, le=30)
    max_concurrency: int = Field(default=8, ge=1, le=100)
    clients: dict[str, UUID] = Field(default_factory=dict)
    auto_provision_tss: bool = False
    auto_provision_clients: bool = False
    admin_pin: SecretStr | None = None
    puk_directory: Path | None = None

    @model_validator(mode="after")
    def validate_provisioning(self):
        if self.tss_id is None and not self.auto_provision_tss:
            raise ValueError("Fiskaly requires a TSS ID or automatic TSS provisioning")
        if self.tss_id is not None and self.tss_id.version != 4:
            raise ValueError("Fiskaly TSS IDs must be UUIDv4")
        if self.auto_provision_tss or self.auto_provision_clients:
            if self.admin_pin is None or len(self.admin_pin.get_secret_value()) < 6:
                raise ValueError("Fiskaly provisioning requires an admin PIN of at least six characters")
        if self.auto_provision_tss and (self.puk_directory is None or not self.puk_directory.is_absolute()):
            raise ValueError("Automatic TSS provisioning requires an absolute secure PUK directory")
        return self

    @field_validator("clients")
    @classmethod
    def validate_clients(cls, value: dict[str, UUID]) -> dict[str, UUID]:
        if any(not key.isdigit() or int(key) <= 0 or str(int(key)) != key for key in value):
            raise ValueError("Fiskaly client bindings require positive canonical till IDs")
        if any(client.version != 4 for client in value.values()) or len(set(value.values())) != len(value):
            raise ValueError("Fiskaly clients require unique UUIDv4 IDs")
        return value

    @field_validator("api_key", "api_secret")
    @classmethod
    def validate_credentials(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Fiskaly credentials must not be empty")
        return value


class FiskalySettings(BaseModel):
    management: FiskalyManagementSettings = Field(default_factory=FiskalyManagementSettings)
    profiles: dict[str, FiskalyConfig] = Field(default_factory=dict)

    @field_validator("profiles")
    @classmethod
    def validate_profiles(cls, value: dict[str, FiskalyConfig]) -> dict[str, FiskalyConfig]:
        tss_ids = [profile.tss_id for profile in value.values() if profile.tss_id is not None]
        if len(set(tss_ids)) != len(tss_ids):
            raise ValueError("A Fiskaly TSS must have exactly one credential profile")
        bindings = [till for profile in value.values() for till in profile.clients]
        if len(set(bindings)) != len(bindings):
            raise ValueError("A till must belong to only one Fiskaly profile")
        return value
