import asyncio
import json
import logging
import time
from collections import Counter
from dataclasses import asdict
from uuid import UUID, uuid4

import asyncpg
from sftkit.database import Connection
from sftkit.util import create_task_protected

from stustapay.core.schema.tse import Tse
from stustapay.tse.handler import TSEMasterData, TSESignatureRequest
from stustapay.tse.signature_request import make_signature_request

from .client import (
    FiskalyAdminAuthenticationError,
    FiskalyClient,
    FiskalyError,
    FiskalyHTTPError,
    FiskalyTransportError,
)
from .config import LIVE_UNAVAILABLE, FiskalyConfig
from .provisioning import FiskalyProvisioner
from .secrets import PukStore
from .signing import FiskalySigner, FiskalySigningRequest, FiskalyTransactionMissing

LOGGER = logging.getLogger(__name__)
MAX_SIGNING_ATTEMPTS = 8


def _retry_after(error: Exception) -> float:
    return error.retry_after if isinstance(error, FiskalyHTTPError) else 0


def _retryable_http_error(error: FiskalyHTTPError) -> bool:
    return error.retryable or error.status in {401, 403, 404}


def _is_outage(error: Exception) -> bool:
    return isinstance(error, FiskalyTransportError) or (isinstance(error, FiskalyHTTPError) and error.status >= 500)


class FiskalyWorker:
    """One DB advisory-lock owner per TSE; parallel I/O with durable requests.

    PostgreSQL releases ownership on process/connection loss. Remote writes use
    the committed identity and snapshot, including after a new worker starts.
    """

    def __init__(self, tse: Tse, config: FiskalyConfig):
        self.tse = tse
        self.config = config
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._capacity_error: str | None = None

    def start(self, db_pool: asyncpg.Pool):
        self._task = create_task_protected(self.run(db_pool), f"fiskaly_tse_{self.tse.id}")

    async def stop(self):
        self._stop.set()
        self._wake.set()
        if self._task:
            await self._task

    def notify_maybe_orders_available(self):
        self._wake.set()

    async def resolve_config(self, conn: Connection) -> FiskalyConfig:
        if self.config.environment == "LIVE":
            raise FiskalyError(LIVE_UNAVAILABLE)
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

    async def discover_bindings(self, conn: Connection) -> tuple[dict[str, UUID], set[str]]:
        bindings = dict(self.config.clients)
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

        rows = await conn.fetch(
            "select t.id from till t join node n on n.id=t.node_id "
            "where $1=any(n.parents_until_event_node || n.id) and not n.read_only "
            "and (t.tse_id is null or t.tse_id=$2) and ($3 or t.id=any($4::bigint[])) order by t.id",
            self.tse.node_id,
            self.tse.id,
            self.config.auto_provision_clients,
            [int(till) for till in bindings],
        )
        eligible = {str(row["id"]) for row in rows}
        if not bindings.keys() <= eligible:
            raise FiskalyError("Fiskaly binding references an inaccessible or differently assigned till")

        stored = {
            str(row["till_id"]): row
            for row in await conn.fetch(
                "select till_id,client_id,registered from fiskaly_client_binding where tse_id=$1",
                self.tse.id,
            )
        }
        for row in rows:
            till = str(row["id"])
            previous = stored.get(till)
            if till not in bindings:
                bindings[till] = previous["client_id"] if previous is not None else uuid4()
            elif previous is not None and previous["client_id"] != bindings[till]:
                raise FiskalyError("Fiskaly client binding differs from the persisted identity")
        return bindings, {till for till, row in stored.items() if row["registered"]}

    async def persist_bindings(self, conn: Connection, bindings: dict[str, UUID]):
        async with conn.transaction():
            for till, client_id in bindings.items():
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
                await conn.execute(
                    "insert into fiskaly_client(id,tse_id,serial) values($1,$2,$3) on conflict(id) do nothing",
                    client_id,
                    self.tse.id,
                    till,
                )
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

    async def configure(self, conn: Connection, signer: FiskalySigner, *, refresh: bool = False):
        if signer.client.config.environment == "LIVE":
            raise FiskalyError(LIVE_UNAVAILABLE)
        current = await conn.fetchrow("select status, serial, public_key from tse where id=$1", self.tse.id)
        if current is None or current["status"] == "disabled":
            raise FiskalyError("Fiskaly TSE is disabled or missing")
        managed = self.tse.fiskaly_job_id is not None
        if not managed:
            bindings, registered = await self.discover_bindings(conn)
        master = None
        if not refresh:
            if self.config.auto_provision_tss and current["public_key"] is None:
                assert self.config.puk_directory is not None
                await FiskalyProvisioner(signer.client).ensure_tss(PukStore(self.config.puk_directory))
            master = await signer.initialize()
            if current["public_key"] is not None and (
                current["public_key"] != master.tse_public_key or current["serial"] != master.tse_serial
            ):
                raise FiskalyError("Fiskaly TSS identity differs from the recorded TSE")

        if managed:
            lock = f"fiskaly:deployments:{self.tse.id}"
            await conn.execute("select pg_advisory_lock(hashtextextended($1,0))", lock)
            try:
                await self.configure_managed_bindings(conn, signer, current["public_key"] is None)
            finally:
                await conn.execute("select pg_advisory_unlock(hashtextextended($1,0))", lock)
            if master is not None:
                await self.save_master_data(conn, master)
            return

        pending = {till: client for till, client in bindings.items() if till not in registered}
        capacity = signer.max_registered_clients
        skipped: list[str] = []
        if capacity is not None and len(registered) + len(pending) > capacity and pending:
            if current["public_key"] is None or not self.config.auto_provision_clients:
                raise FiskalyError("Fiskaly event exceeds the TSS registered-client capacity")
            available = max(0, capacity - len(registered))
            candidates = sorted(pending, key=int)
            skipped = candidates[available:]
            pending = {till: pending[till] for till in candidates[:available]}
        capacity_error = (
            f"Fiskaly TSS client capacity reached. Unassigned tills: {', '.join(skipped)}" if skipped else None
        )

        # Only reserve space for tills we can actually register.
        if pending:
            await self.persist_bindings(conn, pending)
        if not refresh:
            verify = {
                till: client
                for till, client in bindings.items()
                if not self.config.auto_provision_clients or till in registered
            }
            results = await asyncio.gather(
                *(signer.verify_client(client_id, till) for till, client_id in verify.items()),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
        if self.config.auto_provision_clients and pending:
            provisioner = FiskalyProvisioner(signer.client)
            async with provisioner.admin_session():
                for till, client_id in pending.items():
                    await provisioner.ensure_client(client_id, till)

        async with conn.transaction():
            status = await conn.fetchval("select status from tse where id=$1 for update", self.tse.id)
            if status is None or status == "disabled":
                raise FiskalyError("Fiskaly TSE is disabled or missing")
            assigned = (
                pending if refresh else {till: client for till, client in bindings.items() if till not in skipped}
            )
            for till in assigned:
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
            if master is not None:
                await self.save_master_data(conn, master)
            if capacity_error != self._capacity_error or master is not None:
                await self.record_health(conn, capacity_error)
        self._capacity_error = capacity_error

    async def save_master_data(self, conn: Connection, master: TSEMasterData):
        await conn.execute(
            "update tse set status='active',serial=$2,hashalgo=$3,time_format=$4,public_key=$5,"
            "certificate=$6,process_data_encoding=$7 where id=$1 and status<>'disabled'",
            self.tse.id,
            master.tse_serial,
            master.tse_hashalgo,
            master.tse_time_format,
            master.tse_public_key,
            master.tse_certificate,
            master.tse_process_data_encoding,
        )

    async def configure_managed_bindings(self, conn: Connection, signer: FiskalySigner, initial: bool):
        # The TSE advisory lock serializes allocation and remote client state changes.
        tills = await conn.fetch(
            "select m.till_id, m.active, b.client_id from fiskaly_managed_till m "
            "left join fiskaly_client_binding b on b.tse_id=m.tse_id and b.till_id=m.till_id "
            "where m.tse_id=$1 order by m.till_id",
            self.tse.id,
        )
        clients = {
            row["id"]: row
            for row in await conn.fetch(
                "select id,serial,registered from fiskaly_client where tse_id=$1 order by serial", self.tse.id
            )
        }
        active_tills = [row for row in tills if row["active"]]
        capacity = signer.max_registered_clients
        if initial and capacity is not None and len(active_tills) > capacity:
            raise FiskalyError("Fiskaly deployment exceeds the TSS registered-client capacity")
        required = {row["client_id"] for row in active_tills if row["client_id"] is not None}
        in_flight = await conn.fetch(
            "with unsettled as ("
            "select b.client_id,b.till_id from fiskaly_client_binding b join ordr o on o.till_id=b.till_id "
            "join tse_signature s on s.id=o.id where b.tse_id=$1 and (s.signature_status='new' "
            "or (s.signature_status='pending' and s.tse_id=b.tse_id and s.fiskaly_client_id=b.client_id)) "
            "union select x.client_id,x.till_id from fiskaly_checkout x where x.tse_id=$1 "
            "and x.start_attempted_at is not null and not x.finished and not exists("
            "select 1 from ordr o join tse_signature s on s.id=o.id "
            "where o.uuid=x.sale_uuid and s.signature_status='done')) "
            "select u.client_id, bool_or(not coalesce(m.deregistration_due,false)) as keep_registered "
            "from unsettled u left join fiskaly_managed_till m on m.tse_id=$1 and m.till_id=u.till_id "
            "group by u.client_id",
            self.tse.id,
        )
        demand = Counter(row["client_id"] for row in active_tills)
        # Expired clients with unresolved work can be deregistered but cannot be reassigned.
        busy = required | {row["client_id"] for row in in_flight}
        keep_registered = required | {row["client_id"] for row in in_flight if row["keep_registered"]}
        inactive = [
            client_id for client_id, row in clients.items() if row["registered"] and client_id not in keep_registered
        ]
        provisioner = FiskalyProvisioner(signer.client)
        if inactive:
            async with provisioner.admin_session():
                for client_id in inactive:
                    await provisioner.set_client_state(client_id, clients[client_id]["serial"], registered=False)
                    await conn.execute("update fiskaly_client set registered=false where id=$1", client_id)
        registered = sum(row["registered"] for row in clients.values()) - len(inactive)
        pending = []
        ready = []
        skipped = []
        free = iter(client_id for client_id in clients if client_id not in busy)
        for row in active_tills:
            till_id = row["till_id"]
            client_id = row["client_id"]
            # A paused deployment keeps its original fiscal identity. It can resume
            # once the other deployment using that client has paused.
            if client_id is not None and demand[client_id] > 1:
                skipped.append(till_id)
                continue
            if client_id is None:
                client_id = next(free, None)
            already_registered = (
                client_id is not None and clients[client_id]["registered"] and client_id not in inactive
            )
            if not already_registered and capacity is not None and registered >= capacity:
                skipped.append(till_id)
                continue
            if row["client_id"] is None:
                async with conn.transaction():
                    if client_id is None:
                        client_id = uuid4()
                        serial = str(till_id)
                        await conn.execute(
                            "insert into fiskaly_client(id,tse_id,serial) values($1,$2,$3)",
                            client_id,
                            self.tse.id,
                            serial,
                        )
                    else:
                        serial = clients[client_id]["serial"]
                    await conn.execute(
                        "insert into fiskaly_client_binding(tse_id,till_id,client_id) values($1,$2,$3)",
                        self.tse.id,
                        till_id,
                        client_id,
                    )
            else:
                serial = clients[client_id]["serial"]
            if not already_registered:
                registered += 1
                pending.append((client_id, serial))
            ready.append(till_id)
        if pending:
            async with provisioner.admin_session():
                for client_id, serial in pending:
                    await provisioner.ensure_client(client_id, serial, reactivate=True)
                    await conn.execute("update fiskaly_client set registered=true where id=$1", client_id)
        for till_id in ready:
            async with conn.transaction():
                assigned = await conn.fetchrow(
                    "update till set tse_id=$2 where id=$1 and tse_id is null and exists("
                    "select 1 from fiskaly_managed_till where till_id=$1 and tse_id=$2 and active) returning z_nr",
                    till_id,
                    self.tse.id,
                )
                if assigned is not None:
                    await conn.execute(
                        "insert into till_tse_history(till_id,tse_id,what,z_nr) values($1,$2,'register',$3)",
                        str(till_id),
                        self.tse.id,
                        assigned["z_nr"],
                    )
                await conn.execute(
                    "update fiskaly_client_binding set registered=true where till_id=$1 and tse_id=$2",
                    till_id,
                    self.tse.id,
                )
        await conn.execute(
            "update fiskaly_provisioning_job j set status='ready',step='complete',last_error=null,updated_at=now() "
            "where j.tse_id=$1 and j.id<>$2 and j.status='retry_wait' and j.step='tse_and_clients' and not j.paused "
            "and not exists(select 1 from fiskaly_managed_till m where m.job_id=j.id and m.active "
            "and not (m.till_id=any($3::bigint[])))",
            self.tse.id,
            self.tse.fiskaly_job_id,
            ready,
        )
        self._capacity_error = f"Fiskaly clients unavailable for tills {skipped}" if skipped else None
        await self.record_health(conn, self._capacity_error)

    async def record_health(self, conn: Connection, capacity_error: str | None):
        await conn.execute(
            "update tse set last_error=coalesce($2, (select 'Fiskaly order ' || s.id || ' needs reconciliation' "
            "from tse_signature s where s.tse_id=$1 and s.signature_status='pending' "
            "and s.fiskaly_next_attempt='infinity' order by s.id limit 1)) where id=$1",
            self.tse.id,
            capacity_error,
        )

    async def advance_checkouts(self, conn: Connection, signer: FiskalySigner):
        rows = await conn.fetch(
            "select x.*, c.serial from fiskaly_checkout x join fiskaly_client c on c.id=x.client_id "
            "where x.tse_id=$1 and not x.finished and x.next_attempt<=clock_timestamp() and "
            "(not exists(select 1 from ordr where uuid=x.sale_uuid) or "
            "(x.start_attempted_at is not null and exists(select 1 from ordr o "
            "join tse_signature s on s.id=o.id where o.uuid=x.sale_uuid and s.signature_status='failure'))) and "
            "((x.start_attempted_at is null and not x.abort_requested) or x.abort_requested or "
            "((x.created_at<clock_timestamp()-interval '15 minutes' or exists("
            "select 1 from fiskaly_managed_till m where m.till_id=x.till_id and m.tse_id=x.tse_id and not m.active)) "
            "and not exists("
            "select 1 from pending_sumup_order where uuid=x.sale_uuid and status='pending'))) "
            "order by x.created_at limit $2",
            self.tse.id,
            self.config.max_concurrency,
        )
        for row in rows:
            await self.advance_checkout(conn, signer, row)

    async def advance_checkout(self, conn: Connection, signer: FiskalySigner, row: asyncpg.Record):
        sale_id = row["sale_uuid"]
        async with conn.transaction():
            await conn.execute("select pg_advisory_xact_lock(hashtextextended($1,0))", str(sale_id))
            claimed = await conn.fetchrow(
                "update fiskaly_checkout x set "
                "abort_requested=(x.abort_requested or x.start_attempted_at is not null or exists("
                "select 1 from fiskaly_till_outage a where a.tse_id=x.tse_id and a.till_id=x.till_id "
                "and (a.ended_at is null or x.created_at between a.started_at and a.ended_at)) or exists("
                "select 1 from fiskaly_managed_till m where m.till_id=x.till_id and m.tse_id=x.tse_id and not m.active)), "
                "start_attempted_at=coalesce(x.start_attempted_at,clock_timestamp()) "
                "where sale_uuid=$1 and not finished and (not exists(select 1 from ordr where uuid=$1) "
                "or (x.start_attempted_at is not null and exists(select 1 from ordr o join tse_signature s "
                "on s.id=o.id where o.uuid=$1 and s.signature_status='failure'))) "
                "and (x.abort_requested or x.start_attempted_at is null or not exists("
                "select 1 from pending_sumup_order where uuid=$1 and status='pending')) returning *",
                sale_id,
            )
        if claimed is None:
            return
        transaction_id = row["transaction_id"]
        try:
            if claimed["abort_requested"]:
                if row["start_attempted_at"] is not None:
                    try:
                        await signer.abort_sale(transaction_id, row["client_id"], row["serial"])
                    except FiskalyHTTPError as exc:
                        if exc.status != 404 or row["started_at"] is not None:
                            raise
                await conn.execute(
                    "update fiskaly_checkout set finished=true,last_error=null where sale_uuid=$1", sale_id
                )
            else:
                # A booking can commit during the bounded network request. The worker will then reconcile this ID.
                await signer.begin_sale(transaction_id, row["client_id"], row["serial"])
                await conn.execute(
                    "update fiskaly_checkout set started_at=clock_timestamp(),last_error=null where sale_uuid=$1",
                    sale_id,
                )
        except FiskalyError as exc:
            if _is_outage(exc):
                await self.record_outage(conn, "TSE unavailable: " + str(exc))
            await conn.execute(
                "update fiskaly_checkout set next_attempt=clock_timestamp()+interval '30 seconds',last_error=$2 "
                "where sale_uuid=$1",
                sale_id,
                str(exc),
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
                "select s.*,o.uuid,o.till_id,t.tse_id as assigned_tse_id from tse_signature s "
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
            checkout = await conn.fetchrow("select * from fiskaly_checkout where sale_uuid=$1", row["uuid"])
            if checkout is not None:
                if checkout["till_id"] != row["till_id"] or checkout["tse_id"] != self.tse.id:
                    raise FiskalyError("TSE unavailable: checkout was assigned to a different register")
                if checkout["abort_requested"] or checkout["start_attempted_at"] is None:
                    raise FiskalyError("TSE unavailable: no fiscal start at checkout")
            outage = await conn.fetchval(
                "select a.reason from fiskaly_till_outage a join ordr o on o.id=$1 "
                "where a.till_id=o.till_id and a.tse_id=$2 "
                "and (a.ended_at is null or o.booked_at between a.started_at and a.ended_at) "
                "order by a.started_at desc limit 1",
                order_id,
                self.tse.id,
            )
            if outage is not None and checkout is None:
                raise FiskalyError(outage)
            till = str(row["till_id"])
            client = await conn.fetchrow(
                "select b.client_id,c.serial from fiskaly_client_binding b join fiskaly_client c on c.id=b.client_id "
                "where b.tse_id=$1 and b.till_id=$2 and b.registered "
                "and ($3 or (c.registered and exists(select 1 from fiskaly_managed_till m "
                "where m.till_id=b.till_id and m.tse_id=b.tse_id) and not exists("
                "select 1 from fiskaly_client_binding x join fiskaly_managed_till m on m.till_id=x.till_id "
                "and m.tse_id=x.tse_id where x.client_id=b.client_id and x.till_id<>b.till_id and m.active)))",
                self.tse.id,
                int(till),
                self.tse.fiskaly_job_id is None,
            )
            if client is None or (checkout is not None and client["client_id"] != checkout["client_id"]):
                raise FiskalyError("Fiskaly till has no configured client binding")
            request = await make_signature_request(conn, order_id, client["serial"])
            transaction_id = checkout["transaction_id"] if checkout is not None else uuid4()
            prepared = FiskalySigningRequest(transaction_id, client["client_id"], request)
            await conn.execute(
                "update tse_signature set signature_status='pending',tse_id=$2,"
                "fiskaly_transaction_id=$3,fiskaly_client_id=$4,fiskaly_request=$5::jsonb,fiskaly_checkout=$6 where id=$1",
                order_id,
                self.tse.id,
                prepared.transaction_id,
                prepared.client_id,
                json.dumps(asdict(request)),
                checkout is not None,
            )
            return prepared

    async def process(self, pool: asyncpg.Pool, signer: FiskalySigner, order_id: int):
        try:
            async with pool.acquire() as conn:
                request = await self.prepare(conn, order_id)
                flags = await conn.fetchrow(
                    "with prior as (select id,fiskaly_start_attempted from tse_signature where id=$1 for update) "
                    "update tse_signature s set fiskaly_attempts=s.fiskaly_attempts+1,fiskaly_start_attempted=true "
                    "from prior where s.id=prior.id returning not prior.fiskaly_start_attempted as allow_start,"
                    "s.fiskaly_checkout",
                    order_id,
                )
            assert flags is not None
            if flags["fiskaly_checkout"]:
                result = await signer.sign(request, checkout=True)
            else:
                result = await signer.sign(request, allow_start=flags["allow_start"])
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
                if flags["fiskaly_checkout"]:
                    await conn.execute(
                        "update fiskaly_checkout set finished=true,last_error=null where transaction_id=$1",
                        request.transaction_id,
                    )
                await self.record_health(conn, self._capacity_error)
        except (FiskalyError, ValueError, RuntimeError) as exc:
            retry = isinstance(exc, FiskalyTransportError) or (
                isinstance(exc, FiskalyHTTPError) and _retryable_http_error(exc)
            )
            retry_after = _retry_after(exc)
            message = str(exc) if isinstance(exc, FiskalyError) else "Fiskaly request preparation failed"
            async with pool.acquire() as conn:
                if _is_outage(exc):
                    await self.record_outage(conn, "TSE unavailable: " + message)
                if isinstance(exc, FiskalyTransactionMissing) and await conn.fetchval(
                    "update fiskaly_checkout x set finished=true,last_error=$2 from ordr o "
                    "join tse_signature s on s.id=o.id where o.id=$1 and x.sale_uuid=o.uuid "
                    "and s.fiskaly_checkout and x.started_at is null returning true",
                    order_id,
                    message,
                ):
                    await conn.execute(
                        "update tse_signature set signature_status='failure',"
                        "result_message='TSE unavailable: missing checkout start' where id=$1 and signature_status='pending'",
                        order_id,
                    )
                    return
                parked = await conn.fetchval(
                    "update tse_signature set fiskaly_last_error=$3, fiskaly_next_attempt="
                    "case when not $4 or fiskaly_attempts >= $5 then 'infinity'::timestamptz "
                    "else now()+greatest($6::double precision,least(60,greatest(2,fiskaly_attempts*2)))"
                    "*interval '1 second' end "
                    "where id=$1 and tse_id=$2 and signature_status='pending' and fiskaly_transaction_id is not null "
                    "returning fiskaly_next_attempt='infinity'",
                    order_id,
                    self.tse.id,
                    message,
                    retry,
                    MAX_SIGNING_ATTEMPTS,
                    retry_after,
                )
                if parked is None:
                    await conn.execute(
                        "update tse_signature s set signature_status='failure',result_message=$2,tse_id=$3 "
                        "where id=$1 and signature_status='new' and exists "
                        "(select 1 from ordr o join till t on t.id=o.till_id where o.id=s.id and t.tse_id=$3)",
                        order_id,
                        message,
                        self.tse.id,
                    )
                elif parked:
                    message = f"Fiskaly order {order_id} needs reconciliation: {message}"
                    LOGGER.error("%s", message)
                await conn.execute("update tse set last_error=$2 where id=$1", self.tse.id, message)
        # Database errors are intentionally allowed to restart the owner loop. If
        # Fiskaly committed before the DB failed, pending recovery queries that UUID.

    async def record_outage(self, conn: Connection, reason: str):
        await conn.execute(
            "insert into fiskaly_till_outage(till_id,tse_id,reason) "
            "select t.id,$1,$2 from till t where t.tse_id=$1 or exists("
            "select 1 from fiskaly_managed_till m where m.till_id=t.id and m.tse_id=$1 and m.active) "
            "on conflict(till_id,tse_id) where ended_at is null do nothing",
            self.tse.id,
            reason,
        )

    async def recover_outage(self, conn: Connection, signer: FiskalySigner):
        if await conn.fetchval(
            "select exists(select 1 from fiskaly_till_outage where tse_id=$1 and ended_at is null)", self.tse.id
        ):
            master = await signer.initialize()
            if not await conn.fetchval(
                "select exists(select 1 from tse where id=$1 and serial=$2 and public_key=$3)",
                self.tse.id,
                master.tse_serial,
                master.tse_public_key,
            ):
                raise FiskalyError("Fiskaly TSS identity differs from the recorded TSE")
            await conn.execute(
                "update fiskaly_till_outage set ended_at=clock_timestamp() where tse_id=$1 and ended_at is null",
                self.tse.id,
            )

    async def drain(self, pool: asyncpg.Pool, signer: FiskalySigner):
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "select s.id from tse_signature s join ordr o on o.id=s.id join till t on t.id=o.till_id "
                "where ((s.signature_status='new' and t.tse_id=$1) "
                "or (s.signature_status='pending' and s.tse_id=$1 and s.fiskaly_transaction_id is not null)) "
                "and s.fiskaly_next_attempt<=now() "
                "and not exists(select 1 from tse_signature prev join ordr po on po.id=prev.id "
                "where po.till_id=o.till_id and prev.id<s.id and prev.signature_status in ('new','pending') "
                "and prev.fiskaly_next_attempt<>'infinity') "
                "order by s.id limit $2",
                self.tse.id,
                self.config.max_concurrency,
            )
        async with asyncio.TaskGroup() as tasks:
            for row in rows:
                tasks.create_task(self.process(pool, signer, row["id"]))
        return bool(rows)

    async def run(self, pool: asyncpg.Pool):
        while not self._stop.is_set():
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
                            provisioning_paused = False
                            while not self._stop.is_set():
                                # Ensure ownership connection is still alive before
                                # scheduling another batch after a remote operation.
                                status = await owner.fetchval("select status from tse where id=$1", self.tse.id)
                                if status == "disabled":
                                    raise FiskalyError("Fiskaly TSE has been disabled")
                                if (
                                    self.config.auto_provision_clients
                                    and not provisioning_paused
                                    and time.monotonic() >= next_provisioning_check
                                ):
                                    delay = 30.0
                                    try:
                                        await self.configure(owner, signer, refresh=True)
                                    except FiskalyError as exc:
                                        LOGGER.error("TSE %s client refresh: %s", self.tse.id, exc)
                                        await owner.execute(
                                            "update tse set last_error=$2 where id=$1", self.tse.id, str(exc)
                                        )
                                        if _is_outage(exc):
                                            await self.record_outage(owner, "TSE unavailable: " + str(exc))
                                        provisioning_paused = isinstance(exc, FiskalyAdminAuthenticationError)
                                        delay = max(delay, _retry_after(exc))
                                    next_provisioning_check = time.monotonic() + delay
                                await self.recover_outage(owner, signer)
                                await self.advance_checkouts(owner, signer)
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
                    if _is_outage(exc):
                        await self.record_outage(conn, "TSE unavailable: " + message)
                if isinstance(exc, FiskalyAdminAuthenticationError):
                    # Repeated PIN failures lock the Fiskaly administrator. A
                    # corrected secret and process restart are required to retry.
                    self._stop.set()
                    return
                try:
                    retry_after = _retry_after(exc)
                    if retry_after > 2:
                        await asyncio.wait_for(self._stop.wait(), retry_after)
                    else:
                        await asyncio.wait_for(self._wake.wait(), 2)
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()
