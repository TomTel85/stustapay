"""
configuration options for fiskaly cloud tses
"""
from stustapay.core.config import FiskalyConfig

class FiskalyCloudTSEConfig(FiskalyConfig):
    serial_number: str
    tss_id: str
    password: str