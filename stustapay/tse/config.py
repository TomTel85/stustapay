from typing import Callable

from stustapay.core.schema.tse import Tse, TseType
from stustapay.core.config import Config

from .diebold_nixdorf_usb.config import DieboldNixdorfUSBTSEConfig
from .diebold_nixdorf_usb.handler import DieboldNixdorfUSBTSE
from .fiskaly_cloud_tse.config import FiskalyCloudTSEConfig
from .fiskaly_cloud_tse.handler import FiskalyCloudTSE
from .handler import TSEHandler


def get_tse_handler(tse: Tse, config: Config) -> Callable[[], TSEHandler]:
    if tse.type == TseType.diebold_nixdorf:
        cfg = DieboldNixdorfUSBTSEConfig(
            serial_number=tse.serial, password=tse.password, ws_url=tse.ws_url, ws_timeout=tse.ws_timeout
        )
        return lambda: DieboldNixdorfUSBTSE(tse.name, cfg)
    
    if tse.type == TseType.fiskaly:
        print(tse.serial)
        cfg = FiskalyCloudTSEConfig(
            serial_number=tse.serial, password=tse.password, tss_id=tse.serial, base_url=config.fiskaly.base_url, api_key=config.fiskaly.api_key, api_secret=config.fiskaly.api_secret, 
        )
        return lambda: FiskalyCloudTSE(tse.name, cfg)

    raise RuntimeError("Unknown tse type")
