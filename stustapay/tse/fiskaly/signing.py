import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from stustapay.tse.handler import TSEMasterData, TSESignature, TSESignatureRequest

from .client import FiskalyClient, FiskalyError, FiskalyHTTPError


@dataclass(frozen=True)
class FiskalySigningRequest:
    """Identity and payload that the worker must persist before remote I/O.

    The same transaction_id, client_id and payload must be reused on recovery.
    A UUID generated only in memory is insufficient for a production worker.
    """

    transaction_id: UUID
    client_id: UUID
    request: TSESignatureRequest

    def __post_init__(self):
        if self.transaction_id.version != 4 or self.client_id.version != 4:
            raise ValueError("Fiskaly transaction and client IDs must be UUIDv4")

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "raw": {
                "process_type": self.request.process_type,
                "process_data": base64.b64encode(self.request.process_data.encode("utf-8")).decode("ascii"),
            }
        }

    @property
    def fingerprint(self) -> str:
        payload = {
            "order_id": self.request.order_id,
            "till_id": self.request.till_id,
            "client_id": str(self.client_id),
            "schema": self.schema,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _timestamp(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise FiskalyError("Fiskaly response has an invalid transaction timestamp")
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (ValueError, OverflowError, OSError):
        raise FiskalyError("Fiskaly response has an invalid transaction timestamp") from None


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise FiskalyError(f"Fiskaly response has no valid {key}")
    return value


def _counter(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).isdigit():
        raise FiskalyError(f"Fiskaly response has no valid {key}")
    return str(value)


class FiskalySigner:
    """Signing for an initialized TSS with pre-provisioned client bindings.

    No TSS or client lifecycle mutations are performed here. The caller owns
    durable state, fiscal lifecycle timing and cross-process work ownership.
    """

    def __init__(self, client: FiskalyClient):
        self.client = client
        self._master_data: TSEMasterData | None = None
        self._in_progress: set[UUID] = set()
        self._concurrency = asyncio.Semaphore(client.config.max_concurrency)
        self.max_registered_clients: int | None = None

    @property
    def _tss_path(self) -> str:
        return f"tss/{self.client.config.tss_id}"

    def _environment(self, data: dict[str, Any]):
        if data.get("_env") != self.client.config.environment:
            raise FiskalyError("Fiskaly resource environment does not match configuration")

    async def initialize(self) -> TSEMasterData:
        self._master_data = None
        data = await self.client.request("GET", self._tss_path)
        self._environment(data)
        if data.get("_id") != str(self.client.config.tss_id) or data.get("state") != "INITIALIZED":
            raise FiskalyError("Fiskaly TSS is not the configured initialized TSS")
        if data.get("transaction_data_encoding") != "UTF-8" or data.get("signature_timestamp_format") != "unixTime":
            raise FiskalyError("Fiskaly TSS uses an unsupported encoding or timestamp format")
        capacity = data.get("max_number_registered_clients")
        if capacity is not None:
            if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
                raise FiskalyError("Fiskaly TSS reports an invalid client capacity")
            self.max_registered_clients = capacity
        self._master_data = TSEMasterData(
            tse_serial=_text(data, "serial_number"),
            tse_hashalgo=_text(data, "signature_algorithm"),
            tse_time_format=_text(data, "signature_timestamp_format"),
            tse_public_key=_text(data, "public_key"),
            tse_certificate=_text(data, "certificate"),
            tse_process_data_encoding=_text(data, "transaction_data_encoding"),
        )
        return self._master_data

    async def verify_client(self, client_id: UUID, till_serial: str):
        if client_id.version != 4:
            raise ValueError("Fiskaly client ID must be UUIDv4")
        data = await self.client.request("GET", f"{self._tss_path}/client/{client_id}")
        self._environment(data)
        if (
            data.get("_id") != str(client_id)
            or data.get("tss_id") != str(self.client.config.tss_id)
            or data.get("state") != "REGISTERED"
            or data.get("serial_number") != till_serial
        ):
            raise FiskalyError("Fiskaly client does not match the configured till binding")

    def _validate_transaction(self, data: dict[str, Any], request: FiskalySigningRequest):
        self._environment(data)
        assert self._master_data is not None
        if (
            data.get("_id") != str(request.transaction_id)
            or data.get("tss_id") != str(self.client.config.tss_id)
            or data.get("client_id") != str(request.client_id)
            or data.get("client_serial_number") != request.request.till_id
            or data.get("tss_serial_number") != self._master_data.tse_serial
        ):
            raise FiskalyError("Fiskaly transaction does not match the persisted identity")
        if data.get("state") not in {"ACTIVE", "FINISHED"}:
            raise FiskalyError("Fiskaly transaction cannot be finished in its current state")
        metadata = data.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("stustapay_payload_sha256") != request.fingerprint:
            raise FiskalyError("Fiskaly transaction does not match the persisted signing payload fingerprint")
        if data.get("state") == "FINISHED" and data.get("schema") != request.schema:
            raise FiskalyError("Fiskaly transaction does not match the persisted signing payload")

    def _signature(self, data: dict[str, Any]) -> TSESignature:
        assert self._master_data is not None
        signature = data.get("signature")
        if not isinstance(signature, dict):
            raise FiskalyError("Fiskaly finished transaction has no signature")
        if (
            signature.get("algorithm") != self._master_data.tse_hashalgo
            or signature.get("public_key") != self._master_data.tse_public_key
        ):
            raise FiskalyError("Fiskaly signature does not match TSS master data")
        encoded_signature = _text(signature, "value")
        try:
            if not base64.b64decode(encoded_signature, validate=True):
                raise ValueError("Empty signature")
        except ValueError:
            raise FiskalyError("Fiskaly signature has invalid Base64 encoding") from None
        start = _timestamp(data.get("time_start"))
        end = _timestamp(data.get("time_end"))
        if end < start:
            raise FiskalyError("Fiskaly transaction ends before its start")
        return TSESignature(
            tse_transaction=_counter(data, "number"),
            tse_signaturenr=_counter(signature, "counter"),
            tse_start=start,
            tse_end=end,
            tse_signature=encoded_signature,
        )

    async def sign(self, request: FiskalySigningRequest) -> TSESignature:
        if self._master_data is None:
            raise FiskalyError("Fiskaly signer must be initialized before signing")
        if request.transaction_id in self._in_progress:
            raise FiskalyError("Fiskaly transaction is already being processed by this signer")
        self._in_progress.add(request.transaction_id)
        try:
            async with self._concurrency:
                return await self._sign(request)
        finally:
            self._in_progress.remove(request.transaction_id)

    async def _sign(self, request: FiskalySigningRequest) -> TSESignature:
        path = f"{self._tss_path}/tx/{request.transaction_id}"
        try:
            data = await self.client.request("GET", path)
        except FiskalyHTTPError as exc:
            if exc.status != 404:
                raise
            # Only a definitive absence permits a new start. Reuse UUID and revision
            # after unknown outcomes; never allocate another transaction here.
            data = await self.client.request(
                "PUT",
                f"{path}?tx_revision=1",
                payload={
                    "state": "ACTIVE",
                    "client_id": str(request.client_id),
                    "metadata": {"stustapay_payload_sha256": request.fingerprint},
                },
            )
        self._validate_transaction(data, request)
        if data["state"] == "FINISHED":
            return self._signature(data)
        # This signer performs exactly start + finish; unexpected updates require
        # explicit operator/worker reconciliation rather than guessing a revision.
        if data.get("latest_revision") != 1 or data.get("revision") != 1:
            raise FiskalyError("Fiskaly transaction has an unexpected active revision")
        data = await self.client.request(
            "PUT",
            f"{path}?tx_revision=2",
            payload={"state": "FINISHED", "client_id": str(request.client_id), "schema": request.schema},
        )
        self._validate_transaction(data, request)
        if data["state"] != "FINISHED":
            raise FiskalyError("Fiskaly did not finish the transaction")
        return self._signature(data)
