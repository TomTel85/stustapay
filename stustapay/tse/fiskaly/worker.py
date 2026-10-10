import asyncio
import json
import logging
import time
from dataclasses import asdict
from uuid import UUID, uuid4

import asyncpg
from sftkit.database import Connection
from sftkit.util import create_task_protected

from stustapay.core.schema.tse import Tse
from stustapay.tse.handler import TSESignatureRequest
from stustapay.tse.signature_request import make_signature_request

from .client import (
    FiskalyAdminAuthenticationError,
    FiskalyClient,
    FiskalyError,
    FiskalyHTTPError,
    FiskalyTransportError,
)
from .config import FiskalyConfig
from .provisioning import FiskalyProvisioner
from .secrets import PukStore
from .signing import FiskalySigner, FiskalySigningRequest

LOGGER = logging.getLogger(__name__)


def _retryable_http_error(error: FiskalyHTTPError) -> bool:
    return error.retryable or error.status in {401, 403, 404}


class FiskalyWorker:
    """One DB advisory-lock owner per TSE; parallel I/O with durable requests.

    PostgreSQL releases ownership on process/connection loss. Remote writes use
    the committed identity and snapshot, including after a new worker starts.
    """

    def __init__(self, tse: Tse, config: FiskalyConfig):
        self.tse = tse
        self.config = config
        self._stop = False
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self, db_pool: asyncpg.Pool):
        self._task = create_task_protected(self.run(db_pool), f"fiskaly_tse_{self.tse.id}")

    async def stop(self):
        self._stop = True
        self._wake.set()
        if self._task:
            await self._task

    def notify_maybe_orders_available(self):
        self._wake.set()

    async def resolve_config(self, conn: Connection) -> FiskalyConfig:
        async with conn.transaction():
            row = await conn.fetchrow("select fiskaly_tss_id,status from tse where id=$1 for update", self.tse.id)
            if row is None or row["status"] == "disabled":
                raise FiskalyError("Fiskaly TSE is disabled or missing")
            tss_id = row["fiskaly_tss_id"]
            if tss_id is not None and self.config.tss_id is not None and tss_id != self.config.tss_id:
                raise FiskalyError("Fiskaly configured TSS differs from the persisted identity")
            if tss_id is None:
                tss_id = self.config.tss_id or uuid4()
                await conn.execute("update tse set fiskaly_tss_id=$2 where id=$1", self.tse.id, tss_id)
        return self.config.model_copy(update={"tss_id": tss_id})

    async def persist_bindings(self, conn: Connection) -> dict[str, UUID]:
        bindings = dict(self.config.clients)
        async with conn.transaction():
            if self.config.customer_node_id is not None:
                allowed_customer = await conn.fetchval(
                    "select exists(select 1 from node where id=$1 and not read_only and $2=any(parent_ids || id))",
                    self.tse.node_id,
                    self.config.customer_node_id,
                )
                if not allowed_customer or self.config.organization_id is None:
                    raise FiskalyError("Fiskaly TSE is outside its configured customer organization")
            if self.config.auto_provision_tss or self.config.auto_provision_clients:
                event = await conn.fetchval(
                    "select event_node_id from node where id=$1 and not read_only", self.tse.node_id
                )
                if event is None:
                    raise FiskalyError("Automatic Fiskaly provisioning requires a writable event node")
            for till in bindings:
                allowed = await conn.fetchval(
                    "select t.id from till t join node n on n.id=t.node_id "
                    "where t.id=$1 and $2=any(n.parents_until_event_node || n.id) and not n.read_only "
                    "and (t.tse_id is null or t.tse_id=$3) for update of t",
                    int(till),
                    self.tse.node_id,
                    self.tse.id,
                )
                if allowed is None:
                    raise FiskalyError("Fiskaly binding references an inaccessible or differently assigned till")
            if self.config.auto_provision_clients:
                rows = await conn.fetch(
                    "select t.id from till t join node n on n.id=t.node_id "
                    "where $1=any(n.parents_until_event_node || n.id) and not n.read_only "
                    "and (t.tse_id is null or t.tse_id=$2) order by t.id for update of t",
                    self.tse.node_id,
                    self.tse.id,
                )
                for row in rows:
                    if str(row["id"]) not in bindings:
                        previous = await conn.fetchval(
                            "select client_id from fiskaly_client_binding where tse_id=$1 and till_id=$2",
                            self.tse.id,
                            row["id"],
                        )
                        bindings[str(row["id"])] = previous or uuid4()
            for till, client_id in bindings.items():
                await conn.execute(
                    "insert into fiskaly_client_binding(tse_id,till_id,client_id) values($1,$2,$3) "
                    "on conflict(tse_id,till_id) do nothing",
                    self.tse.id,
                    int(till),
                    client_id,
                )
                previous = await conn.fetchval(
                    "select client_id from fiskaly_client_binding where tse_id=$1 and till_id=$2",
                    self.tse.id,
                    int(till),
                )
                if previous != client_id:
                    raise FiskalyError("Fiskaly client binding differs from the persisted identity")
        return bindings

    async def configure(self, conn: Connection, signer: FiskalySigner):
        current = await conn.fetchrow("select status, serial, public_key from tse where id=$1", self.tse.id)
        if current is None or current["status"] == "disabled":
            raise FiskalyError("Fiskaly TSE is disabled or missing")
        # Validate visibility and commit every client identity before provisioning.
        bindings = await self.persist_bindings(conn)
        # A previously initialized fiscal identity must never be re-created if
        # the provider suddenly reports it missing (e.g. TEST data was wiped).
        if self.config.auto_provision_tss and current["public_key"] is None:
            assert self.config.puk_directory is not None
            await FiskalyProvisioner(signer.client).ensure_tss(PukStore(self.config.puk_directory))
        master = await signer.initialize()
        if signer.max_registered_clients is not None and len(bindings) > signer.max_registered_clients:
            raise FiskalyError("Fiskaly event exceeds the TSS registered-client capacity")
        if current["public_key"] is not None and (
            current["public_key"] != master.tse_public_key or current["serial"] != master.tse_serial
        ):
            raise FiskalyError("Fiskaly TSS identity differs from the recorded TSE")
        if self.config.auto_provision_clients:
            provisioner = FiskalyProvisioner(signer.client)
            pending = await conn.fetch(
                "select till_id,client_id from fiskaly_client_binding where tse_id=$1 and not registered",
                self.tse.id,
            )
            pending = [row for row in pending if str(row["till_id"]) in bindings]
            if pending:
                async with provisioner.admin_session():
                    for row in pending:
                        await provisioner.ensure_client(row["client_id"], str(row["till_id"]))
        await asyncio.gather(*(signer.verify_client(client, till) for till, client in bindings.items()))
        async with conn.transaction():
            for till in bindings:
                row = await conn.fetchrow(
                    "select t.tse_id, t.z_nr from till t join node n on n.id=t.node_id "
                    "where t.id=$1 and $2=any(n.parents_until_event_node || n.id) and not n.read_only "
                    "for update of t",
                    int(till),
                    self.tse.node_id,
                )
                if row is None or row["tse_id"] not in {None, self.tse.id}:
                    raise FiskalyError("Fiskaly binding references an inaccessible or differently assigned till")
                if row["tse_id"] is None:
                    await conn.execute("update till set tse_id=$1 where id=$2", self.tse.id, int(till))
                    await conn.execute(
                        "insert into till_tse_history(till_id,tse_id,what,z_nr) values($1,$2,'register',$3)",
                        till,
                        self.tse.id,
                        row["z_nr"],
                    )
                await conn.execute(
                    "update fiskaly_client_binding set registered=true where tse_id=$1 and till_id=$2",
                    self.tse.id,
                    int(till),
                )
            await conn.execute(
                "update tse set status='active',serial=$2,hashalgo=$3,time_format=$4,public_key=$5,"
                "certificate=$6,process_data_encoding=$7,last_error=null where id=$1",
                self.tse.id,
                master.tse_serial,
                master.tse_hashalgo,
                master.tse_time_format,
                master.tse_public_key,
                master.tse_certificate,
                master.tse_process_data_encoding,
            )

    async def prepare(self, conn: Connection, order_id: int) -> FiskalySigningRequest:
        async with conn.transaction():
            if self.config.customer_node_id is not None and not await conn.fetchval(
                "select exists(select 1 from node where id=$1 and not read_only and $2=any(parent_ids || id))",
                self.tse.node_id,
                self.config.customer_node_id,
            ):
                raise FiskalyError("Fiskaly event is outside its configured customer scope")
            row = await conn.fetchrow(
                "select s.*,o.till_id,t.tse_id as assigned_tse_id from tse_signature s "
                "join ordr o on o.id=s.id join till t on t.id=o.till_id "
                "where s.id=$1 for update of s",
                order_id,
            )
            if row is None or row["signature_status"] not in {"new", "pending"}:
                raise FiskalyError("Fiskaly signing request is no longer pending")
            if row["fiskaly_transaction_id"] is not None:
                if row["tse_id"] != self.tse.id:
                    raise FiskalyError("Fiskaly persisted transaction belongs to a different TSE")
                payload = row["fiskaly_request"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return FiskalySigningRequest(
                    row["fiskaly_transaction_id"], row["fiskaly_client_id"], TSESignatureRequest(**payload)
                )
            if row["signature_status"] != "new" or row["assigned_tse_id"] != self.tse.id:
                raise FiskalyError("Fiskaly signing request has no valid till assignment")
            till = str(row["till_id"])
            client_id = await conn.fetchval(
                "select client_id from fiskaly_client_binding where tse_id=$1 and till_id=$2 and registered",
                self.tse.id,
                int(till),
            )
            if client_id is None:
                raise FiskalyError("Fiskaly till has no configured client binding")
            request = await make_signature_request(conn, order_id, till)
            prepared = FiskalySigningRequest(uuid4(), client_id, request)
            await conn.execute(
                "update tse_signature set signature_status='pending',tse_id=$2,"
                "fiskaly_transaction_id=$3,fiskaly_client_id=$4,fiskaly_request=$5::jsonb where id=$1",
                order_id,
                self.tse.id,
                prepared.transaction_id,
                prepared.client_id,
                json.dumps(asdict(request)),
            )
            return prepared

    async def process(self, pool: asyncpg.Pool, signer: FiskalySigner, order_id: int):
        try:
            async with pool.acquire() as conn:
                request = await self.prepare(conn, order_id)
                await conn.execute("update tse_signature set fiskaly_attempts=fiskaly_attempts+1 where id=$1", order_id)
            result = await signer.sign(request)
            async with pool.acquire() as conn:
                await conn.execute(
                    "update tse_signature set signature_status='done',result_message='success',"
                    "transaction_process_type=$2,transaction_process_data=$3,tse_transaction=$4,tse_signaturenr=$5,"
                    "tse_start=$6,tse_end=$7,tse_signature=$8,fiskaly_last_error=null "
                    "where id=$1 and signature_status='pending' and tse_id=$9",
                    order_id,
                    request.request.process_type,
                    request.request.process_data,
                    result.tse_transaction,
                    result.tse_signaturenr,
                    result.tse_start,
                    result.tse_end,
                    result.tse_signature,
                    self.tse.id,
                )
                await conn.execute("update tse set last_error=null where id=$1", self.tse.id)
        except (FiskalyError, ValueError, RuntimeError) as exc:
            retry = isinstance(exc, FiskalyTransportError) or (
                isinstance(exc, FiskalyHTTPError) and _retryable_http_error(exc)
            )
            message = str(exc) if isinstance(exc, FiskalyError) else "Fiskaly request preparation failed"
            async with pool.acquire() as conn:
                if retry:
                    await conn.execute(
                        "update tse_signature set fiskaly_last_error=$2,"
                        "fiskaly_next_attempt=now()+least(60,greatest(2,fiskaly_attempts*2))*interval '1 second' "
                        "where id=$1 and signature_status in ('new','pending')",
                        order_id,
                        message,
                    )
                else:
                    await conn.execute(
                        "update tse_signature set signature_status='failure',result_message=$2,tse_id=$3 "
                        "where id=$1 and signature_status in ('new','pending')",
                        order_id,
                        message,
                        self.tse.id,
                    )
                await conn.execute("update tse set last_error=$2 where id=$1", self.tse.id, message)
        # Database errors are intentionally allowed to restart the owner loop. If
        # Fiskaly committed before the DB failed, pending recovery queries that UUID.

    async def drain(self, pool: asyncpg.Pool, signer: FiskalySigner):
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "select s.id from tse_signature s join ordr o on o.id=s.id join till t on t.id=o.till_id "
                "where ((s.signature_status='new' and t.tse_id=$1) "
                "or (s.signature_status='pending' and s.tse_id=$1 and s.fiskaly_transaction_id is not null)) "
                "and s.fiskaly_next_attempt<=now() "
                "and not exists(select 1 from tse_signature prev join ordr po on po.id=prev.id "
                "where po.till_id=o.till_id and prev.id<s.id and prev.signature_status in ('new','pending')) "
                "order by s.id limit $2",
                self.tse.id,
                self.config.max_concurrency,
            )
        await asyncio.gather(*(self.process(pool, signer, row["id"]) for row in rows))
        return bool(rows)

    async def run(self, pool: asyncpg.Pool):
        while not self._stop:
            try:
                async with pool.acquire() as owner:
                    lock = f"stustapay:fiskaly:{self.tse.id}"
                    if not await owner.fetchval("select pg_try_advisory_lock(hashtextextended($1,0))", lock):
                        await asyncio.sleep(2)
                        continue
                    try:
                        resolved_config = await self.resolve_config(owner)
                        async with FiskalyClient(resolved_config) as client:
                            signer = FiskalySigner(client)
                            await self.configure(owner, signer)
                            next_provisioning_check = time.monotonic() + 30
                            while not self._stop:
                                # Ensure ownership connection is still alive before
                                # scheduling another batch after a remote operation.
                                status = await owner.fetchval("select status from tse where id=$1", self.tse.id)
                                if status == "disabled":
                                    raise FiskalyError("Fiskaly TSE has been disabled")
                                if self.config.auto_provision_clients and time.monotonic() >= next_provisioning_check:
                                    await self.configure(owner, signer)
                                    next_provisioning_check = time.monotonic() + 30
                                if await self.drain(pool, signer):
                                    continue
                                try:
                                    await asyncio.wait_for(self._wake.wait(), 2)
                                except asyncio.TimeoutError:
                                    pass
                                self._wake.clear()
                    finally:
                        await owner.execute("select pg_advisory_unlock(hashtextextended($1,0))", lock)
            except Exception as exc:
                message = str(exc) if isinstance(exc, FiskalyError) else "Fiskaly worker unavailable"
                LOGGER.error("TSE %s: %s", self.tse.id, message)
                async with pool.acquire() as conn:
                    await conn.execute("update tse set last_error=$2 where id=$1", self.tse.id, message)
                if isinstance(exc, FiskalyAdminAuthenticationError):
                    # Repeated PIN failures lock the Fiskaly administrator. A
                    # corrected secret and process restart are required to retry.
                    self._stop = True
                    return
                try:
                    await asyncio.wait_for(self._wake.wait(), 2)
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()
