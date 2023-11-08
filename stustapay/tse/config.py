from typing import Callable

from stustapay.core.schema.tse import Tse, TseType

from .diebold_nixdorf_usb.config import DieboldNixdorfUSBTSEConfig
from .diebold_nixdorf_usb.handler import DieboldNixdorfUSBTSE
from .fiskaly_cloud_tse.config import FiskalyCloudTSEConfig
from .fiskaly_cloud_tse.handler import FiskalyCloudTSE
from .handler import TSEHandler


def get_tse_handler(tse: Tse) -> Callable[[], TSEHandler]:
    if tse.type == TseType.diebold_nixdorf:
        cfg = DieboldNixdorfUSBTSEConfig(
            serial_number=tse.serial, password=tse.password, ws_url=tse.ws_url, ws_timeout=tse.ws_timeout
        )
        return lambda: DieboldNixdorfUSBTSE(tse.name, cfg)
    
    if tse.type == TseType.fiskaly:
        print(tse.serial)
        cfg = FiskalyCloudTSEConfig(
            serial_number=tse.serial, password=tse.password, base_url="https://kassensichv-middleware.fiskaly.com/api/v2", tss_id="1a463a31-242a-4a96-a444-1e64a9cabf9c", api_key="test_3yncqmxb69vd2x5ap3imlgtsw_tfcashless", api_secret="leCvUlv5Rcu5SV7zCCCX6GIiyG6IzguSlNPFPnvcNuf"
        )
        return lambda: FiskalyCloudTSE(tse.name, cfg)

    raise RuntimeError("Unknown tse type")
