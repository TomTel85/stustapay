"""Wire contracts for bounded, opt-in offline tag sales."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from stustapay.core.schema.order import CompletedSale, NewSale
from stustapay.core.schema.product import Product, ProductRestriction


class OfflineLimits(BaseModel):
    validity_seconds: int = Field(default=7200, ge=60, le=86400)
    sale_per_transaction_cents: int = Field(default=2000, ge=0)
    sale_per_customer_cents: int = Field(default=3000, ge=0)
    sale_per_till_cents: int = Field(default=50000, ge=0)
    return_per_transaction_cents: int = Field(default=2000, ge=0)
    return_per_customer_cents: int = Field(default=3000, ge=0)
    return_per_till_cents: int = Field(default=50000, ge=0)


class OfflineCustomer(BaseModel):
    customer_account_id: int
    customer_tag_uid: int
    balance_cents: int
    restriction: ProductRestriction | None = None


class OfflineButton(BaseModel):
    id: int
    name: str
    products: list[Product]


class OfflineSnapshot(BaseModel):
    id: UUID
    server_time: datetime
    valid_until: datetime
    terminal_id: int
    till_id: int
    event_node_id: int
    user_id: int
    rules: OfflineLimits
    customers: list[OfflineCustomer]
    buttons: list[OfflineButton]


class OfflineBooking(BaseModel):
    snapshot_id: UUID
    sale: NewSale
    sequence: int = Field(ge=1)
    recorded_at: AwareDatetime


class OfflineImport(BaseModel):
    bookings: list[OfflineBooking] = Field(max_length=100)


class OfflineBookingStatus(str, Enum):
    booked = "booked"
    already_booked = "already_booked"
    clarification_required = "clarification_required"
    not_found = "not_found"
    dismissed = "dismissed"


class OfflineBookingResult(BaseModel):
    uuid: UUID
    status: OfflineBookingStatus
    sale: CompletedSale | None = None
    message: str | None = None


class OfflineImportResult(BaseModel):
    results: list[OfflineBookingResult]


class OfflineReportEntry(BaseModel):
    uuid: UUID
    snapshot_id: UUID
    terminal_id: int
    till_id: int
    user_id: int
    recorded_at: datetime
    received_at: datetime
    status: OfflineBookingStatus
    message: str | None = None
    customer_account_id: int | None = None
    new_balance: float | None = None
    order_id: int | None = None


class OfflineDeviceStatus(BaseModel):
    terminal_id: int
    till_id: int
    user_id: int
    snapshot_id: UUID
    last_contact_at: datetime
    valid_until: datetime
