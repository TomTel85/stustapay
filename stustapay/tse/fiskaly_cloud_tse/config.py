"""
configuration options for fiskaly cloud tses
"""

from pydantic import BaseModel


class FiskalyCloudTSEConfig(BaseModel):
    base_url: str
    api_key: str
    api_secret: str
    serial_number: str
    tss_id: str
    password: str