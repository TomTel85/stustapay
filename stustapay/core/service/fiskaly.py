"""Tenant-scoped onboarding commands. Provider I/O runs outside API transactions."""

from uuid import uuid4

import asyncpg
from sftkit.database import Connection
from sftkit.error import InvalidArgument, NotFound
from sftkit.service import Service, with_db_transaction

from stustapay.core.config import Config
from stustapay.core.schema.fiskaly import (
    FiskalyProvisioningJob,
    FiskalySite,
    NewFiskalyProvisioningJob,
    NewFiskalySite,
)
from stustapay.core.schema.tree import Node, ObjectType
from stustapay.core.schema.user import Privilege
from stustapay.core.service.auth import AuthService
from stustapay.core.service.common.decorators import requires_node, requires_root_user, requires_user
from stustapay.tse.fiskaly.config import LIVE_UNAVAILABLE


class FiskalyService(Service[Config]):
    def __init__(self, db_pool: asyncpg.Pool, config: Config, auth_service: AuthService):
        super().__init__(db_pool, config)
        self.auth_service = auth_service

    @with_db_transaction(read_only=True)
    @requires_node()
    @requires_user([Privilege.node_administration])
    async def list_sites(self, *, conn: Connection, node: Node) -> list[FiskalySite]:
        return await conn.fetch_many(
            FiskalySite,
            "select s.* from fiskaly_site s join node n on n.id=s.customer_node_id "
            "where s.customer_node_id=any($1) or $2=any(n.parent_ids || n.id) order by s.name,s.id",
            node.ids_to_root,
            node.id,
        )

    @with_db_transaction
    @requires_node()
    @requires_root_user([Privilege.node_administration])
    async def create_site(self, *, conn: Connection, node: Node, site: NewFiskalySite) -> FiskalySite:
        del node
        # Root is the provider, never an operational customer.
        target = await conn.fetchrow("select * from node where id=$1 and not read_only", site.customer_node_id)
        if target is None or site.customer_node_id == 0:
            raise InvalidArgument("Select a writable customer node below the provider root")
        await conn.execute("select pg_advisory_xact_lock(hashtextextended('fiskaly:customer-tree',0))")
        vat_id = site.vat_id.strip().upper() if site.vat_id else None
        duplicate = await conn.fetchval(
            "select exists(select 1 from fiskaly_site where "
            "($1::text is not null and upper(trim(vat_id))=$1) "
            "or lower(trim(operator_name))=lower($2) "
            "and country_code=$3 and zip=$4 and lower(trim(address_line1))=lower($5))",
            vat_id or None,
            site.operator_name,
            site.country_code,
            site.zip,
            site.address_line1,
        )
        if duplicate:
            raise InvalidArgument("A Fiskaly taxpayer with these details already exists")
        return await conn.fetch_one(
            FiskalySite,
            "insert into fiskaly_site(customer_node_id,identity,name,operator_name,address_line1,zip,town,"
            "country_code,vat_id) values($1,$2,$3,$4,$5,$6,$7,$8,$9) returning *",
            site.customer_node_id,
            uuid4(),
            site.name,
            site.operator_name,
            site.address_line1,
            site.zip,
            site.town,
            site.country_code,
            vat_id or None,
        )

    @with_db_transaction(read_only=True)
    @requires_node()
    @requires_user([Privilege.node_administration])
    async def site_status(self, *, conn: Connection, node: Node, site_id: int) -> list[FiskalyProvisioningJob]:
        return await conn.fetch_many(
            FiskalyProvisioningJob,
            "select j.*, (select count(distinct b.client_id) from fiskaly_managed_till m "
            "join fiskaly_client_binding b on b.till_id=m.till_id and b.tse_id=m.tse_id "
            "join fiskaly_client c on c.id=b.client_id and c.registered "
            "where m.job_id=j.id and e.end_date<=now() "
            "and date_trunc('month', e.end_date at time zone 'Europe/Berlin') < "
            "date_trunc('month', (now()+interval '48 hours') at time zone 'Europe/Berlin') "
            "and not exists(select 1 from fiskaly_client_binding other "
            "join fiskaly_managed_till a on a.till_id=other.till_id and a.tse_id=other.tse_id "
            "where other.client_id=b.client_id and a.active)) as month_end_registered_clients "
            "from fiskaly_provisioning_job j join node n on n.id=j.scope_node_id "
            "join node event_node on event_node.id=j.event_node_id join event e on e.id=event_node.event_id "
            "where j.site_id=$1 and (n.id=any($2) or $3=any(n.parent_ids || n.id)) order by j.id desc",
            site_id,
            node.ids_to_root,
            node.id,
        )

    @with_db_transaction
    @requires_node()
    @requires_root_user([Privilege.node_administration])
    async def start_provisioning(
        self,
        *,
        conn: Connection,
        node: Node,
        request: NewFiskalyProvisioningJob,
    ) -> FiskalyProvisioningJob:
        del node
        management = self.config.fiskaly.management
        if not management.enabled or request.environment not in management.environments:
            raise InvalidArgument("Fiskaly management is not configured for the requested environment")
        site = await conn.fetchrow("select * from fiskaly_site where id=$1", request.site_id)
        event = await conn.fetchrow("select * from node_with_allowed_objects where id=$1", request.event_node_id)
        scope = await conn.fetchrow(
            "select * from node_with_allowed_objects where id=$1", request.scope_node_id or request.event_node_id
        )
        if site is None or event is None or scope is None:
            raise InvalidArgument("Fiskaly site or event does not exist")
        customer = await conn.fetchrow("select * from node where id=$1", site["customer_node_id"])
        if (
            event["event_node_id"] != request.event_node_id
            or scope["event_node_id"] != event["id"]
            or site["customer_node_id"] not in [*scope["parent_ids"], scope["id"]]
            or event["read_only"]
            or scope["read_only"]
            or customer["read_only"]
            or ObjectType.tse.value in event["computed_forbidden_objects_at_node"]
        ):
            raise InvalidArgument("Select a writable event belonging to the site's customer")
        group_id = management.environments[request.environment].group_id
        if site["group_id"] is not None and site["group_id"] != group_id:
            raise InvalidArgument("Fiskaly site belongs to a different provider group")
        await conn.execute("select pg_advisory_xact_lock(hashtextextended($1,0))", f"fiskaly:event:{event['id']}")
        existing = await conn.fetch_maybe_one(
            FiskalyProvisioningJob,
            "select * from fiskaly_provisioning_job where scope_node_id=$1",
            scope["id"],
        )
        if existing is not None:
            if existing.site_id != request.site_id or existing.environment != request.environment:
                raise InvalidArgument("An event cannot change its provisioned Fiskaly site or environment")
            return existing
        if request.environment == "LIVE":
            raise InvalidArgument(LIVE_UNAVAILABLE)
        if await conn.fetchval(
            "select exists(select 1 from fiskaly_provisioning_job j join node n on n.id=j.scope_node_id "
            "where j.event_node_id=$1 and (n.id=any($2::bigint[]) or $3=any(n.parent_ids))) "
            "or exists(select 1 from tse t join node n on n.id=t.node_id "
            "where t.fiskaly_job_id is null and n.event_node_id=$1 "
            "and (n.id=any($2::bigint[]) or $3=any(n.parent_ids || n.id)))",
            event["id"],
            scope["parent_ids"],
            scope["id"],
        ):
            raise InvalidArgument("The selected scope overlaps an existing TSE assignment")
        return await conn.fetch_one(
            FiskalyProvisioningJob,
            "insert into fiskaly_provisioning_job(site_id,event_node_id,scope_node_id,environment) "
            "values($1,$2,$3,$4) returning *",
            request.site_id,
            request.event_node_id,
            scope["id"],
            request.environment,
        )

    @with_db_transaction
    @requires_node(allow_read_only=True)
    @requires_root_user([Privilege.node_administration])
    async def set_paused(self, *, conn: Connection, node: Node, job_id: int, paused: bool) -> FiskalyProvisioningJob:
        del node
        job = await conn.fetch_maybe_one(
            FiskalyProvisioningJob, "select * from fiskaly_provisioning_job where id=$1", job_id
        )
        if job is None:
            raise NotFound(element_type="fiskaly_provisioning_job", element_id=str(job_id))
        if job.status != "ready" or job.tse_id is None:
            raise InvalidArgument("Pause or resume is available after provisioning has completed")
        await conn.execute("select pg_advisory_xact_lock(hashtextextended($1,0))", f"fiskaly:deployments:{job.tse_id}")
        if not paused and await conn.fetchval(
            "select scope.read_only or e.read_only or customer.read_only "
            "from fiskaly_provisioning_job j join node scope on scope.id=j.scope_node_id "
            "join node e on e.id=j.event_node_id join fiskaly_site s on s.id=j.site_id "
            "join node customer on customer.id=s.customer_node_id where j.id=$1",
            job_id,
        ):
            raise InvalidArgument("An archived deployment cannot be resumed")
        if not paused and await conn.fetchval(
            "select e.end_date <= now() from node n join event e on e.id=n.event_id where n.id=$1",
            job.event_node_id,
        ):
            raise InvalidArgument("A deployment cannot be resumed after the event end")
        if not paused and await conn.fetchval(
            "select exists(select 1 from fiskaly_managed_till m "
            "join fiskaly_client_binding b on b.tse_id=m.tse_id and b.till_id=m.till_id "
            "join fiskaly_client_binding other on other.client_id=b.client_id "
            "join fiskaly_managed_till a on a.till_id=other.till_id and a.tse_id=other.tse_id "
            "where m.job_id=$1 and a.job_id<>$1 and a.active)",
            job_id,
        ):
            raise InvalidArgument("A different deployment is using one of these fiscal clients")
        return await conn.fetch_one(
            FiskalyProvisioningJob,
            "update fiskaly_provisioning_job set paused=$2,updated_at=now() where id=$1 returning *",
            job_id,
            paused,
        )

    @with_db_transaction
    @requires_node()
    @requires_root_user([Privilege.node_administration])
    async def retry_provisioning(self, *, conn: Connection, node: Node, job_id: int) -> FiskalyProvisioningJob:
        del node
        job = await conn.fetch_maybe_one(
            FiskalyProvisioningJob,
            "select * from fiskaly_provisioning_job where id=$1 for update",
            job_id,
        )
        if job is None:
            raise NotFound(element_type="fiskaly_provisioning_job", element_id=str(job_id))
        if job.status in {"ready", "running", "queued"}:
            return job
        if job.environment == "LIVE":
            raise InvalidArgument(LIVE_UNAVAILABLE)
        if (
            not self.config.fiskaly.management.enabled
            or job.environment not in self.config.fiskaly.management.environments
        ):
            raise InvalidArgument("Fiskaly management is not configured for this environment")
        return await conn.fetch_one(
            FiskalyProvisioningJob,
            "update fiskaly_provisioning_job set status='queued',next_attempt_at=now(),last_error=null,"
            "replace_unfinished_key=(step='key_secret_missing'),attempts=0,updated_at=now() where id=$1 returning *",
            job_id,
        )
