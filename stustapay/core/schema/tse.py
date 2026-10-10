import enum
from typing import Optional

from pydantic import BaseModel


class TseStatus(enum.Enum):
    new = "new"
    active = "active"
    disabled = "disabled"
    failed = "failed"


class TseType(enum.Enum):
    diebold_nixdorf = "diebold_nixdorf"
    fiskaly = "fiskaly"


class UpdateTse(BaseModel):
    name: str
    ws_url: str = ""
    ws_timeout: float = 5
    password: str = ""
    fiskaly_profile: Optional[str] = None


class NewTse(UpdateTse):
    type: TseType
    serial: Optional[str] = None


class Tse(NewTse):
    node_id: int
    id: int
    status: TseStatus
    hashalgo: Optional[str]
    time_format: Optional[str]
    public_key: Optional[str]
    certificate: Optional[str]
    process_data_encoding: Optional[str]
    last_error: Optional[str] = None
    fiskaly_job_id: Optional[int] = None
