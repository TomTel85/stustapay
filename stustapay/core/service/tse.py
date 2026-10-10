import asyncpg
from sftkit.database import Connection
from sftkit.error import InvalidArgument, NotFound
from sftkit.service import Service, with_db_transaction

from stustapay.core.config import Config
from stustapay.core.schema.tree import Node, ObjectType
from stustapay.core.schema.tse import NewTse, Tse, TseType, UpdateTse
from stustapay.core.schema.user import CurrentUser, Privilege
from stustapay.core.service.auth import AuthService
from stustapay.core.service.common.decorators import requires_node, requires_user


async def list_tses(conn: Connection, node: Node) -> list[Tse]:
    return await conn.fetch_many(Tse, "select * from tse where node_id = any($1) order by name", node.ids_to_event_node)


class TseService(Service[Config]):
    def __init__(self, db_pool: asyncpg.Pool, config: Config, auth_service: AuthService):
        super().__init__(db_pool, config)
        self.auth_service = auth_service

    def _validate_profile(self, tse_type: TseType, profile: str | None):
        if tse_type == TseType.fiskaly:
            if not profile or profile not in self.config.fiskaly.profiles:
                raise InvalidArgument("Fiskaly requires an existing server credential profile")
        elif profile is not None:
            raise InvalidArgument("Fiskaly profiles are only supported by Fiskaly TSEs")

    async def _validate_customer_profile(self, conn: Connection, node: Node, user: CurrentUser, profile: str | None):
        if profile is None:
            return
        config = self.config.fiskaly.profiles[profile]
        if config.customer_node_id is not None:
            if config.customer_node_id not in node.ids_to_root or config.organization_id is None:
                raise InvalidArgument("Fiskaly profile is not bound to this customer and organization")
            return
        provider = await conn.fetchval(
            "select exists(select 1 from user_to_role utr join user_role_with_privileges urwp on utr.role_id=urwp.id "
            "where utr.node_id=0 and urwp.node_id=0 and utr.user_id=$1 and 'node_administration'=any(urwp.privileges))",
            user.id,
        )
        if not provider:
            raise InvalidArgument("Unbound Fiskaly profiles require provider administration")

    @with_db_transaction
    @requires_node(object_types=[ObjectType.tse], event_only=False)
    @requires_user([Privilege.node_administration])
    async def create_tse(self, *, conn: Connection, node: Node, current_user: CurrentUser, new_tse: NewTse) -> Tse:
        self._validate_profile(new_tse.type, new_tse.fiskaly_profile)
        await self._validate_customer_profile(conn, node, current_user, new_tse.fiskaly_profile)
        if node.event_node_id is not None:
            await conn.execute(
                "select pg_advisory_xact_lock(hashtextextended($1,0))",
                f"fiskaly:event:{node.event_node_id}",
            )
        if await conn.fetchval(
            "select exists(select 1 from fiskaly_provisioning_job where event_node_id=$1)",
            node.event_node_id,
        ):
            raise InvalidArgument("This event is managed by automatic Fiskaly onboarding")
        tse_id = await conn.fetchval(
            "insert into tse (node_id, name, serial, ws_url, ws_timeout, password, type, fiskaly_profile, status) "
            "values ($1, $2, $3, $4, $5, $6, $7, $8, 'new') returning id",
            node.id,
            new_tse.name,
            new_tse.serial or "",
            new_tse.ws_url,
            new_tse.ws_timeout,
            new_tse.password,
            new_tse.type.value,
            new_tse.fiskaly_profile,
        )
        return await conn.fetch_one(Tse, "select * from tse where id = $1", tse_id)

    @with_db_transaction
    @requires_node(object_types=[ObjectType.tse], event_only=False)
    @requires_user([Privilege.node_administration])
    async def update_tse(
        self,
        *,
        conn: Connection,
        node: Node,
        current_user: CurrentUser,
        tse_id: int,
        updated_tse: UpdateTse,
    ) -> Tse:
        current = await conn.fetch_maybe_one(
            Tse, "select * from tse where id=$1 and node_id=any($2) for update", tse_id, node.ids_to_event_node
        )
        if current is None:
            raise NotFound(element_type="tse", element_id=str(tse_id))
        managed = await conn.fetchval("select fiskaly_job_id from tse where id=$1", tse_id)
        if managed is not None and updated_tse.fiskaly_profile != current.fiskaly_profile:
            raise InvalidArgument("Automatic Fiskaly TSE credential assignments cannot be changed")
        if managed is None:
            self._validate_profile(current.type, updated_tse.fiskaly_profile)
            await self._validate_customer_profile(conn, node, current_user, updated_tse.fiskaly_profile)
        if current.fiskaly_profile != updated_tse.fiskaly_profile:
            used = await conn.fetchval(
                "select exists(select 1 from tse_signature where tse_id=$1) "
                "or exists(select 1 from tse where id=$1 and fiskaly_tss_id is not null)",
                tse_id,
            )
            if current.status.value != "new" or used:
                raise InvalidArgument("An initialized or used TSE cannot change Fiskaly profile")
        tse_id = await conn.fetchval(
            "update tse set name = $1, ws_timeout = $2, ws_url = $3, password = $4, fiskaly_profile=$7 "
            "where id = $5 and node_id = any($6) returning id",
            updated_tse.name,
            updated_tse.ws_timeout,
            updated_tse.ws_url,
            updated_tse.password,
            tse_id,
            node.ids_to_event_node,
            updated_tse.fiskaly_profile,
        )
        if tse_id is None:
            raise NotFound(element_type="tse", element_id=str(tse_id))
        return await conn.fetch_one(Tse, "select * from tse where id = $1", tse_id)

    @with_db_transaction(read_only=True)
    @requires_node(event_only=False)
    @requires_user([Privilege.node_administration])
    async def list_tses(self, *, conn: Connection, node: Node) -> list[Tse]:
        return await list_tses(conn=conn, node=node)
