import asyncio
import base64
import binascii
import contextlib
import uuid
import logging
import typing
from datetime import datetime, timezone

import aiohttp
import pytz
from dateutil import parser

from stustapay.core.util import create_task_protected
from stustapay.tse.fiskaly_cloud_tse.config import FiskalyCloudTSEConfig
from stustapay.tse.handler import (
    TSEHandler,
    TSEMasterData,
    TSESignature,
    TSESignatureRequest,
)



LOGGER = logging.getLogger(__name__)


class RequestError(RuntimeError):
    def __init__(self, name: str, request: dict, response: dict):
        self.name = name
        try:
            self.code: typing.Optional[int] = int(response["Code"])
        except (KeyError, ValueError):
            self.code = None
        self.description = response.get("Description")
        super().__init__(f"{name!r}: request {request} failed: {self.description} (code {self.code})")


class FiskalyCloudTSE(TSEHandler):
    def __init__(self, name: str, config: FiskalyCloudTSEConfig):
        self.base_url = config.base_url
        self.api_key = config.api_key
        self.api_secret = config.api_secret
        self.background_task: typing.Optional[asyncio.Task] = None
        self.request_id = 0
        self.pending_requests: dict[int, asyncio.Future[dict]] = {}
        self.password: str = config.password
        self.tss_id: str = config.tss_id
        self.headers: dict = {}
        self.serial_number: str = config.serial_number
        self._stop = asyncio.Event()  # set this to request all tasks to stop
        self._name = name
        self._signature_algorithm: typing.Optional[str] = None
        self._log_time_format: typing.Optional[str] = None
        self._public_key: typing.Optional[str] = None  # base64
        self._certificate: typing.Optional[str] = None  # long string

    async def get_access_token(self):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/auth",
                json={"api_key": self.api_key, "api_secret": self.api_secret},
            ) as response:
                data = await response.json()
                if response.status != 200:
                    raise Exception(f"Error {data['error']}: {data['message']}")
                return data["access_token"]

    

    async def start(self) -> bool:
        start_result: asyncio.Future[bool] = asyncio.Future()
        self.background_task = create_task_protected(self.run(start_result), f"run_task {self}", self._stop.set)
        return await start_result

    async def stop(self):
        # TODO cleanly cancel the background task
        self._stop.set()
        if self.background_task is not None:
            await self.background_task

    async def get_device_data(self) -> str:
        result = await self.request(method="GET",endpoint=f"/tss/{self.tss_id}")
        return result

    async def run(self, start_result: asyncio.Future[bool]):

            device_info = await self.get_device_data()
            if self.serial_number != device_info["_id"]:
                raise RuntimeError(
                    f"wrong serial number: expected {self.serial_number}, but device has serial number {device_info['_id']}"
                )
            self._log_time_format = device_info["signature_timestamp_format"]
            if self._log_time_format == "UnixTime":
                self._log_time_format = "unixTime"  # ¯\_(ツ)_/¯

            self._signature_algorithm = device_info["signature_algorithm"]
            self._public_key = device_info["public_key"]
            self._certificate = device_info["certificate"] 

            start_result.set_result(True)

            while not self._stop.is_set():
                #await self.request("PingPong")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=2)
                except asyncio.TimeoutError:
                    pass

    async def request(self, method: str, endpoint: str, payload=None, headers=None):
            url = f"{self.base_url}{endpoint}"
            token = await self.get_access_token()
            
            auth_header = {
                'Authorization': f'Bearer {token}'
                }
            self.headers.update(auth_header)    
            # If headers are provided, merge them with the default headers
            if headers:
                self.headers.update(headers)

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.request(method, url, headers=self.headers, json=payload) as response:
                        response.raise_for_status()
                        response = await response.json()

                except aiohttp.ClientError as e:
                    print("aiohttp client error", e)
                except aiohttp.http.HttpProcessingError as e:
                    print("aiohttp processing error", e)
                except asyncio.TimeoutError as e:
                    print("asyncio timeout error", e)
                except Exception as e:
                    print("generic error", e)
                finally:
                    return response
    

    async def authenticate_admin(self):
        headers = {
                'Content-Type': 'application/json',
                }
                    
        payload = {
	    "admin_pin": f"{self.password}"
        }
        await self.request(method="POST",endpoint=f"/tss/{self.tss_id}/admin/auth",payload=payload, headers=headers)

    async def logout_admin(self):
        payload = {
        }
        await self.request(method="POST",endpoint=f"/tss/{self.tss_id}/admin/logout", payload=payload)


    async def retrieve_client(self,client_id: str):
        client = await self.request(method="GET",endpoint=f"/tss/{self.tss_id}/client/{client_id}") 
        return client   
    

    async def register_client_id(self,client_id: str):
        payload = {
        "serial_number": f"ERS {client_id}",
        "metadata": {
            "custom_field": "custom_value"
        }
        }
        await self.request(method="PUT",endpoint=f"/tss/{self.tss_id}/client/{client_id}",payload=payload)

    async def deregister_client_id(self,client_id: str):
        payload = {
        "state": "DEREGISTERED"
        }
        await self.request(method="PATCH",endpoint=f"/tss/{self.tss_id}/client/{client_id}",payload=payload)
    
    async def start_transaction(self, transaction_payload: str, tx_revision: str):
        transaction_id = uuid.uuid4()
        print(f"Start transaction {transaction_id}")
        data = await self.request("PUT",endpoint=f"/tss/{self.tss_id}/tx/{transaction_id}?tx_revision={tx_revision}", payload=transaction_payload)
        return data

        
    async def finish_transaction(self, transaction_id, transaction_payload: str, tx_revision: str):
        print(f"Finish transaction {transaction_id}")
        data = await self.request(method="PUT", endpoint=f"/tss/{self.tss_id}/tx/{transaction_id}?tx_revision={tx_revision}", payload=transaction_payload)
        return data




    async def sign(self, request: TSESignatureRequest, fiskaly_uuid: str) -> TSESignature:

        start_payload = {
            "state": "ACTIVE",
            "client_id": str(fiskaly_uuid)
        }

        encoded_data = base64.b64encode(request.process_data.encode('utf-8')).decode('utf-8')

        payload = {
            "schema": {
                "raw": {
                    "process_type": request.process_type,
                    "process_data": encoded_data
                }
            },
            "state": "ACTIVE",
            "client_id": str(fiskaly_uuid)  # Assuming fiskaly_uuid is a UUID object.
        }
        tx_revision=1
        start_result = await self.start_transaction(transaction_payload=start_payload,tx_revision=tx_revision)
        transaction_number = start_result["_id"]
        tx_revision=int(start_result["latest_revision"])+1
        finish_result = await self.finish_transaction(
            transaction_id=transaction_number,
            transaction_payload=payload,
            tx_revision=tx_revision
        )
        return TSESignature(
            tse_transaction=transaction_number,
            tse_signaturenr=finish_result["signature"]["counter"],
            tse_start=datetime.utcfromtimestamp(start_result["log"]["timestamp"]).replace(tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z', # convert to isoformat in UTC YYYY-mm-ddTHH:MM:ss.000Z
            tse_end=datetime.utcfromtimestamp(finish_result["log"]["timestamp"]).replace(tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            tse_signature=finish_result["signature"]["value"],
        )

    def get_master_data(self) -> TSEMasterData:
        assert self._signature_algorithm is not None
        assert self._log_time_format is not None
        assert self._public_key is not None
        assert self._certificate is not None
        return TSEMasterData(
            tse_serial=self.serial_number,
            tse_hashalgo=self._signature_algorithm,
            tse_time_format=self._log_time_format,
            tse_public_key=self._public_key,
            tse_certificate=self._certificate,
            tse_process_data_encoding="UTF-8",
        )

    async def get_client_ids(self) -> list[str]:
        result = await self.request(method="GET",endpoint=f"/tss/{self.tss_id}/client",payload={})
        client_ids = [entry['_id'] for entry in result['data']] 
        # try:
        #     result = result["data"]
        # except KeyError:
        #     raise RuntimeError(f"{self._name!r}: GetDeviceStatus did not return ClientIDs") from None
        # if not isinstance(result, list) or any(not isinstance(x, str) for x in result):
        #     raise RuntimeError(f"{self}: GetDeviceStatus returned bad result: {result}")
        # try:
        #     # hide the default dummy client id
        #     result.remove("DummyDefaultClientId")
        # except ValueError:
        #     raise RuntimeError("TSE does not have 'DummyDefaultClientId' registered") from None
        # clientid_to_ignore = set()
        # for entry in result:
        #     if entry.startswith("DN TSEProduction"):
        #         clientid_to_ignore.add(entry)
        # for entry in clientid_to_ignore:
        #     result.remove(entry)

        return client_ids

    def is_stop_set(self):
        return self._stop.is_set()

    def __str__(self):
        return self._name
