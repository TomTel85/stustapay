"""Durable managed-organization onboarding and dynamic credential resolution."""

import asyncio
import secrets
from typing import Any
from uuid import UUID, uuid4

import asyncpg
from pydantic import SecretStr
from sftkit.database import Connection

from stustapay.core.config import Config
from stustapay.core.schema.tse import Tse

from .client import FiskalyClient, FiskalyError, FiskalyHTTPError, FiskalyTransportError
from .config import LIVE_UNAVAILABLE, FiskalyConfig
from .management import FiskalyManagementClient
from .secrets import CredentialVault
from .signing import FiskalySigner
from .worker import FiskalyWorker


class OnboardingActionRequired(FiskalyError):
    """A provider administrator must reconcile before another remote write."""


def credential_scope(site_id: int, environment: str) -> str:
    return f"fiskaly:site:{site_id}:{environment}"


async def resolve_managed_config(conn: Connection, config: Config, job_id: int) -> FiskalyConfig:
    management = config.fiskaly.management
    if not management.enabled or management.secret_key is None:
        raise FiskalyError("Fiskaly management configuration is unavailable")
    row = await conn.fetchrow(
        "select j.*,s.organization_id,s.customer_node_id,s.group_id,e.credential_ciphertext,"
        "t.fiskaly_tss_id from fiskaly_provisioning_job j join fiskaly_site s on s.id=j.site_id "
        "join fiskaly_site_environment e on e.site_id=s.id and e.environment=j.environment "
        "join tse t on t.id=j.tse_id where j.id=$1",
        job_id,
    )
    if row is None or not row["credential_ciphertext"] or not row["pin_ciphertext"]:
        raise FiskalyError("Fiskaly managed credentials are not ready")
    environment = row["environment"]
    if environment == "LIVE":
        raise FiskalyError(LIVE_UNAVAILABLE)
    provider = management.environments.get(environment)
    if provider is None or provider.group_id != row["group_id"]:
        raise FiskalyError("Fiskaly managed site belongs to a different provider group")
    allowed = await conn.fetchval(
        "select exists(select 1 from node where id=$1 and not read_only and $2=any(parent_ids || id))",
        row["event_node_id"],
        row["customer_node_id"],
    )
    if not allowed:
        raise FiskalyError("Fiskaly managed event no longer belongs to its customer")
    vault = CredentialVault(management.secret_key)
    credentials = vault.decrypt(credential_scope(row["site_id"], environment), row["credential_ciphertext"])
    pin = vault.decrypt(f"fiskaly:job:{job_id}:pin", row["pin_ciphertext"])
    try:
        return FiskalyConfig(
            api_key=SecretStr(credentials["api_key"]),
            api_secret=SecretStr(credentials["api_secret"]),
            organization_id=row["organization_id"],
            customer_node_id=row["customer_node_id"],
            environment=environment,
            tss_id=row["fiskaly_tss_id"],
            admin_pin=SecretStr(pin["admin_pin"]),
            puk_directory=management.puk_directory,
            auto_provision_tss=True,
            auto_provision_clients=True,
        )
    except (KeyError, ValueError):
        raise FiskalyError("Fiskaly managed credential record is invalid") from None


class FiskalyOnboardingRunner:
    """A single advisory owner serializes creation; no DB transaction spans HTTP."""

    def __init__(self, config: Config):
        self.config = config
        key = config.fiskaly.management.secret_key
        if key is None:
            raise FiskalyError("Fiskaly management encryption key is missing")
        self.vault = CredentialVault(key)

    async def run(self, pool: asyncpg.Pool):
        while True:
            async with pool.acquire() as conn:
                lock = "stustapay:fiskaly:onboarding"
                acquired = await conn.fetchval("select pg_try_advisory_lock(hashtextextended($1,0))", lock)
                if acquired:
                    try:
                        row = await conn.fetchrow(
                            "select id from fiskaly_provisioning_job where status in ('queued','running','retry_wait') "
                            "and next_attempt_at<=now() order by next_attempt_at,id limit 1",
                        )
                        if row:
                            await self.process(conn, row["id"])
                    finally:
                        await conn.execute("select pg_advisory_unlock(hashtextextended($1,0))", lock)
            await asyncio.sleep(2)

    async def step(self, conn: Connection, job_id: int, step: str):
        await conn.execute("update fiskaly_provisioning_job set step=$2,updated_at=now() where id=$1", job_id, step)

    async def process(self, conn: Connection, job_id: int):
        job = await conn.fetchrow(
            "update fiskaly_provisioning_job set status='running',attempts=attempts+1,updated_at=now() "
            "where id=$1 and status in ('queued','running','retry_wait') returning *",
            job_id,
        )
        if job is None:
            return
        try:
            if job["environment"] == "LIVE":
                raise OnboardingActionRequired(LIVE_UNAVAILABLE)
            management = self.config.fiskaly.management
            credentials = management.environments.get(job["environment"])
            if not management.enabled or credentials is None:
                raise OnboardingActionRequired("Fiskaly management environment is not configured")
            valid = await conn.fetchval(
                "select exists(select 1 from node n join fiskaly_site s on s.id=$2 "
                "join node c on c.id=s.customer_node_id where n.id=$1 and n.event_node_id=n.id "
                "and not n.read_only and not c.read_only and s.customer_node_id=any(n.parent_ids || n.id))",
                job["event_node_id"],
                job["site_id"],
            )
            if not valid:
                raise OnboardingActionRequired("Fiskaly onboarding event is read-only or outside its customer scope")
            active_count = await conn.fetchval(
                "select count(*) from fiskaly_provisioning_job j join tse t on t.id=j.tse_id "
                "join node n on n.id=j.event_node_id where j.status='ready' and not n.read_only "
                "and t.status<>'disabled' and j.id<>$1",
                job_id,
            )
            if active_count >= management.max_active_tses:
                raise OnboardingActionRequired("Fiskaly controller active-TSE capacity reached")
            async with FiskalyManagementClient(credentials) as client:
                await self.step(conn, job_id, "organization")
                organization_id = await self.ensure_organization(conn, job["site_id"], client)
                await self.step(conn, job_id, "environment")
                organization = await client.get_organization(organization_id)
                if job["environment"] not in organization.get("_envs", []):
                    await client.enable_environment(organization_id)
                    organization = await client.get_organization(organization_id)
                    if job["environment"] not in organization.get("_envs", []):
                        raise OnboardingActionRequired("Fiskaly did not enable the requested environment")
                await self.step(conn, job_id, "credentials")
                await self.ensure_credentials(conn, job, client, organization_id)
            await self.step(conn, job_id, "tse")
            await self.ensure_tse(conn, job)
            cloud = await resolve_managed_config(conn, self.config, job_id)
            tse = await conn.fetch_one(Tse, "select * from tse where fiskaly_job_id=$1", job_id)
            lock = f"stustapay:fiskaly:{tse.id}"
            if not await conn.fetchval("select pg_try_advisory_lock(hashtextextended($1,0))", lock):
                raise FiskalyTransportError("Fiskaly TSE is currently owned by another controller")
            try:
                worker = FiskalyWorker(tse, cloud)
                cloud = await worker.resolve_config(conn)
                worker.config = cloud
                async with FiskalyClient(cloud) as sign_client:
                    await self.step(conn, job_id, "tse_and_clients")
                    await worker.configure(conn, FiskalySigner(sign_client))
            finally:
                await conn.execute("select pg_advisory_unlock(hashtextextended($1,0))", lock)
            await conn.execute(
                "update fiskaly_provisioning_job set status='ready',step='complete',last_error=null,"
                "updated_at=now() where id=$1",
                job_id,
            )
        except Exception as exc:  # Status survives process restart; errors never include upstream bodies.
            retryable = isinstance(exc, FiskalyTransportError)
            if isinstance(exc, FiskalyHTTPError):
                retryable = exc.retryable  # pylint: disable=no-member
            status = "retry_wait" if retryable and job["attempts"] < 8 else "action_required"
            if not isinstance(exc, FiskalyError) or (retryable and job["attempts"] >= 8):
                status = "failed"
            message = (
                str(exc)
                if isinstance(exc, FiskalyError)
                else (f"Fiskaly onboarding could not complete ({type(exc).__name__})")
            )
            await conn.execute(
                "update fiskaly_provisioning_job set status=$2,last_error=$3,next_attempt_at="
                "now()+($4 * interval '1 second'),updated_at=now() where id=$1",
                job_id,
                status,
                message,
                min(300, 2 ** min(job["attempts"], 8)),
            )

    @staticmethod
    def verify_organization(organization: dict[str, Any], group_id: UUID, expected_id: UUID | None = None) -> UUID:
        try:
            identity = UUID(organization["_id"])
        except (KeyError, ValueError, TypeError):
            raise OnboardingActionRequired("Fiskaly returned an invalid organization identity") from None
        if (
            organization.get("managed_by_organization_id") != str(group_id)
            or organization.get("_type") not in {"MANAGED_ORGANIZATION", "ORGANIZATION"}
            or (expected_id is not None and identity != expected_id)
        ):
            raise OnboardingActionRequired("Fiskaly organization is outside the expected provider group")
        return identity

    async def ensure_organization(self, conn: Connection, site_id: int, client: FiskalyManagementClient) -> UUID:
        site = await conn.fetchrow("select * from fiskaly_site where id=$1", site_id)
        assert site is not None
        group_id = client.config.group_id
        if site["group_id"] is not None and site["group_id"] != group_id:
            raise OnboardingActionRequired("Fiskaly site is bound to a different provider group")
        if site["organization_id"] is not None:
            organization = await client.get_organization(site["organization_id"])
            return self.verify_organization(organization, group_id, site["organization_id"])
        identity = str(site["identity"])
        organizations = await client.list_organizations()
        matches = [item for item in organizations if item.get("metadata", {}).get("stustapay_site") == identity]
        if len(matches) > 1:
            raise OnboardingActionRequired("Multiple Fiskaly organizations match this site; reconciliation is required")
        if matches:
            organization = matches[0]
        else:
            if site["creation_started"]:
                raise OnboardingActionRequired(
                    "Fiskaly organization creation outcome is unknown; reconcile before retrying"
                )
            await conn.execute(
                "update fiskaly_site set creation_started=true,group_id=$2 where id=$1",
                site_id,
                group_id,
            )
            payload = {
                "name": site["operator_name"],
                "managed_by_organization_id": str(group_id),
                "address_line1": site["address_line1"],
                "zip": site["zip"],
                "town": site["town"],
                "country_code": site["country_code"],
                "metadata": {"stustapay_site": identity},
            }
            if site["vat_id"]:
                payload["vat_id"] = site["vat_id"]
            try:
                organization = await client.create_organization(payload)
            except FiskalyHTTPError as exc:
                if exc.status in {400, 401, 403, 422, 429}:
                    await conn.execute("update fiskaly_site set creation_started=false where id=$1", site_id)
                raise
        organization_id = self.verify_organization(organization, group_id)
        await conn.execute(
            "update fiskaly_site set organization_id=$2,group_id=$3 where id=$1",
            site_id,
            organization_id,
            group_id,
        )
        return organization_id

    async def ensure_credentials(
        self,
        conn: Connection,
        job: asyncpg.Record,
        client: FiskalyManagementClient,
        organization_id: UUID,
    ):
        site_id, environment = job["site_id"], job["environment"]
        await conn.execute(
            "insert into fiskaly_site_environment(site_id,environment,key_identity) values($1,$2,$3) "
            "on conflict(site_id,environment) do nothing",
            site_id,
            environment,
            uuid4(),
        )
        row = await conn.fetchrow(
            "select * from fiskaly_site_environment where site_id=$1 and environment=$2",
            site_id,
            environment,
        )
        assert row is not None
        if row["credential_ciphertext"]:
            self.vault.decrypt(credential_scope(site_id, environment), row["credential_ciphertext"])
            return
        name = f"ssp-{row['key_identity'].hex[:26]}"
        keys = await client.list_keys(organization_id)
        matches = [key for key in keys if key.get("name") == name]
        if len(matches) > 1:
            raise OnboardingActionRequired("Multiple Fiskaly keys match this onboarding attempt")
        if matches:
            key = matches[0]
            metadata = key.get("metadata") or {}
            if metadata.get("stustapay_key") != str(row["key_identity"]):
                raise OnboardingActionRequired("Fiskaly key ownership could not be verified")
            key_id = UUID(key["_id"])
            if not job["replace_unfinished_key"]:
                await self.step(conn, job["id"], "key_secret_missing")
                raise OnboardingActionRequired(
                    "Fiskaly key secret was not saved; retry explicitly to replace the unfinished key"
                )
            used = await conn.fetchval(
                "select exists(select 1 from fiskaly_provisioning_job where site_id=$1 and environment=$2 "
                "and tse_id is not null)",
                site_id,
                environment,
            )
            if used:
                raise OnboardingActionRequired(
                    "Fiskaly key is associated with a TSE and cannot be replaced automatically"
                )
            await client.disable_key(organization_id, key_id)
            new_identity = uuid4()
            await conn.execute(
                "update fiskaly_site_environment set key_identity=$3,key_id=null,creation_started=false "
                "where site_id=$1 and environment=$2",
                site_id,
                environment,
                new_identity,
            )
            await conn.execute(
                "update fiskaly_provisioning_job set replace_unfinished_key=false where id=$1", job["id"]
            )
            return await self.ensure_credentials(
                conn,
                await conn.fetchrow("select * from fiskaly_provisioning_job where id=$1", job["id"]),
                client,
                organization_id,
            )
        if row["creation_started"]:
            raise OnboardingActionRequired("Fiskaly key creation outcome is unknown; reconcile before retrying")
        await conn.execute(
            "update fiskaly_site_environment set creation_started=true where site_id=$1 and environment=$2",
            site_id,
            environment,
        )
        try:
            key = await client.create_key(organization_id, name, {"stustapay_key": str(row["key_identity"])})
        except FiskalyHTTPError as exc:
            if exc.status in {400, 401, 403, 422, 429}:
                await conn.execute(
                    "update fiskaly_site_environment set creation_started=false where site_id=$1 and environment=$2",
                    site_id,
                    environment,
                )
            raise
        if not isinstance(key.get("key"), str) or not isinstance(key.get("secret"), str) or not key["secret"]:
            await self.step(conn, job["id"], "key_secret_missing")
            raise OnboardingActionRequired("Fiskaly did not return an API key secret")
        ciphertext = self.vault.encrypt(
            credential_scope(site_id, environment),
            {
                "api_key": key["key"],
                "api_secret": key["secret"],
            },
        )
        await conn.execute(
            "update fiskaly_site_environment set key_id=$3,credential_ciphertext=$4 "
            "where site_id=$1 and environment=$2",
            site_id,
            environment,
            UUID(key["_id"]),
            ciphertext,
        )

    async def ensure_tse(self, conn: Connection, job: asyncpg.Record):
        async with conn.transaction():
            current = await conn.fetchrow("select * from fiskaly_provisioning_job where id=$1 for update", job["id"])
            assert current is not None
            if current["tse_id"] is not None:
                return
            # Persist the PIN and TSS identity before any TSS operation.
            ciphertext = self.vault.encrypt(f"fiskaly:job:{job['id']}:pin", {"admin_pin": secrets.token_urlsafe(24)})
            tse_id = await conn.fetchval(
                "insert into tse(node_id,name,serial,ws_url,ws_timeout,password,type,status,fiskaly_job_id,"
                "fiskaly_tss_id) values($1,$2,'','',5,'','fiskaly','new',$3,$4) returning id",
                job["event_node_id"],
                f"Fiskaly {job['environment']} Event {job['event_node_id']}",
                job["id"],
                uuid4(),
            )
            await conn.execute(
                "update fiskaly_provisioning_job set tse_id=$2,pin_ciphertext=$3 where id=$1",
                job["id"],
                tse_id,
                ciphertext,
            )
