import asyncio
import contextlib
import logging

import asyncpg
from sftkit.database import Connection, DatabaseHook

from stustapay.core.config import Config
from stustapay.core.healthcheck import run_healthcheck
from stustapay.core.schema.tse import Tse, TseType

from ..core.database import get_database
from .config import get_tse_handler
from .fiskaly.client import FiskalyError
from .fiskaly.config import LIVE_UNAVAILABLE, FiskalyConfig
from .fiskaly.onboarding import FiskalyOnboardingRunner, resolve_managed_config
from .fiskaly.worker import FiskalyWorker
from .wrapper import TSEWrapper

LOGGER = logging.getLogger(__name__)


class SignatureProcessor:
    def __init__(self, config: Config):
        self.config = config
        self.tses: dict[int, TSEWrapper | FiskalyWorker] = {}
        self.db_pool: asyncpg.Pool | None = None
        # contains event objects for each object that is waiting for new events.

    async def run(self) -> None:
        db = get_database(self.config.database)
        # Cloud owners retain one advisory-lock connection each. Keep additional
        # connections available for short queue transactions and the DB hook.
        self.db_pool = await db.create_pool(
            n_connections=10
            + len(self.config.fiskaly.profiles)
            + (self.config.fiskaly.management.max_active_tses if self.config.fiskaly.management.enabled else 0)
        )

        async with contextlib.AsyncExitStack() as aes:
            # Clean up pending signatures.
            # We have no idea what state the assigned TSE was in when our predecessor
            # process was stopped.
            # In theory, it might be possible to recover them by checking whether the
            # indicated TSE has actually completed the signature and advancing it to
            # 'done' if yes, setting it back to 'new' else.
            # This introduces much complexity and potential for bugs though,
            # so for now we just assume that the signature was interrupted and failed.
            # after this clean-up the database will be in a consistent state where
            # the till <-> tse mapping can be obtained via select name, tse_id from till;
            # see the next request.
            await self.db_pool.execute(
                """
                update
                    tse_signature
                set
                    signature_status='failure',
                    result_message='pending signature was not completed due to signature processor restart'
                where
                    signature_status='pending' and fiskaly_transaction_id is null
                """
            )

            await self.refresh_workers(aes)

            # TODO Task to assign feral tills to a TSE
            LOGGER.info(f"Configured TSEs: {self.tses}")

            db_hook = DatabaseHook(self.db_pool, "tse_signature", self.handle_hook, initial_run=True)
            # Any background failure stops the controller so supervision can restart
            # it; an unnoticed dead onboarding task must never look healthy.
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self.watch_workers(aes))
                tasks.create_task(db_hook.run())
                tasks.create_task(run_healthcheck(db, service_name="tses"))
                if self.config.fiskaly.management.enabled:
                    tasks.create_task(FiskalyOnboardingRunner(self.config).run(self.db_pool))

        await self.db_pool.close()

    async def refresh_workers(self, stack: contextlib.AsyncExitStack):
        assert self.db_pool is not None
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch_many(
                Tse,
                "select t.* from tse t join node n on t.node_id=n.id "
                "left join fiskaly_provisioning_job j on j.id=t.fiskaly_job_id "
                "where (not n.read_only or t.fiskaly_job_id is not null) and t.status<>'disabled' "
                "and (t.fiskaly_job_id is null or j.status='ready') order by t.id",
            )
            active = {row.id for row in rows}
            for tse_id in list(self.tses):
                if tse_id not in active:
                    await self.tses.pop(tse_id).stop()
            managed_count = sum(
                isinstance(worker, FiskalyWorker) and worker.tse.fiskaly_job_id is not None
                for worker in self.tses.values()
            )
            for row in rows:
                if row.id in self.tses:
                    continue
                worker: TSEWrapper | FiskalyWorker
                profile: FiskalyConfig | None
                if row.type == TseType.fiskaly:
                    try:
                        if row.fiskaly_job_id is not None:
                            if managed_count >= self.config.fiskaly.management.max_active_tses:
                                raise FiskalyError("Fiskaly controller active-TSE capacity reached")
                            profile = await resolve_managed_config(conn, self.config, row.fiskaly_job_id)
                        else:
                            profile = self.config.fiskaly.profiles.get(row.fiskaly_profile or "")
                            if profile is None:
                                raise FiskalyError("Fiskaly credential profile unavailable")
                        if profile.environment == "LIVE":
                            raise FiskalyError(LIVE_UNAVAILABLE)
                        worker = FiskalyWorker(row, profile)
                    except FiskalyError as exc:
                        await conn.execute("update tse set last_error=$2 where id=$1", row.id, str(exc))
                        continue
                    if row.fiskaly_job_id is not None:
                        managed_count += 1
                else:
                    worker = TSEWrapper(tse_id=row.id, factory_function=get_tse_handler(row))
                worker.start(self.db_pool)
                stack.push_async_callback(worker.stop)
                self.tses[row.id] = worker

    async def watch_workers(self, stack: contextlib.AsyncExitStack):
        while True:
            await asyncio.sleep(5)
            await self.refresh_workers(stack)

    async def handle_hook(self, payload):
        assert self.db_pool is not None
        del payload  # unused
        LOGGER.info("tse_signature hook")

        # check if it is from a till without an assigned TSE
        async with contextlib.AsyncExitStack() as aes:
            psql: Connection = await aes.enter_async_context(self.db_pool.acquire())

            feral_till_id_rows = await psql.fetch(
                """
                    select
                        till.id as till_id
                    from
                        tse_signature
                        join ordr on ordr.id=tse_signature.id
                        join till on ordr.till_id=till.id
                        join node n on n.id=till.node_id
                    where
                        tse_signature.signature_status='new' and
                        till.tse_id is Null and not(till.id = any($1::bigint[]))
                        and not exists(select 1 from fiskaly_provisioning_job fj
                            where fj.scope_node_id=any(n.parents_until_event_node || n.id))
                        and not exists(select 1 from tse cloud where cloud.type='fiskaly'
                            and cloud.fiskaly_profile=any($2::text[])
                            and cloud.node_id=any(n.parents_until_event_node || n.id))
                    """,
                [int(till) for profile in self.config.fiskaly.profiles.values() for till in profile.clients],
                [name for name, profile in self.config.fiskaly.profiles.items() if profile.auto_provision_clients],
            )
            if feral_till_id_rows is None:
                pass  # all fine
            else:
                LOGGER.info(f"till(s) without TSE but an order {feral_till_id_rows}")
                LOGGER.info(f"{len(feral_till_id_rows)} till(s) need a TSE")
                # assign TSEs
                for till in feral_till_id_rows:
                    # get number of assigned tills per tse, but only of active TSEs
                    tse_stats = dict()
                    active_tses = await psql.fetch(
                        "select tse.id, tse.name from tse join till t on t.id=$1 join node n on n.id=t.node_id "
                        "where tse.status='active' and tse.type='diebold_nixdorf' "
                        "and tse.node_id=any(n.parents_until_event_node || n.id)",
                        till["till_id"],
                    )
                    for tse in active_tses:
                        # TODO optimize this statement for really really large installations...
                        tse_stats[tse["id"]] = await psql.fetchval(
                            "select count(*) from till where tse_id=$1",
                            tse["id"],
                        )
                    tse_ranked = sorted(tse_stats.items(), key=lambda x: x[1])
                    # assign this till to tse with the lowest number
                    till_id_to_assign_to_tse = till["till_id"]
                    try:
                        tse_id = tse_ranked[0][0]
                        await psql.execute(
                            "update till set tse_id = $1 where id = $2", tse_id, till_id_to_assign_to_tse
                        )
                        LOGGER.info(f"Till with ID={till_id_to_assign_to_tse} is assigned to TSE ID {tse_id}")
                    except IndexError:
                        LOGGER.error("ERROR: no more active TSEs available")
                        # Cloud bindings are explicit and may be established by a
                        # starting worker. Do not fail every event or invent TSE 1.
                        LOGGER.warning("Leaving unassigned signing requests queued for explicit TSE configuration")

        # notify all TSEs
        for tse in self.tses.values():
            tse.notify_maybe_orders_available()
