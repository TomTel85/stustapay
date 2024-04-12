from typing import Optional

import asyncpg

from stustapay.core.config import Config
from stustapay.core.schema.terminal import (
    CurrentTerminal,
    NewTerminal,
    Terminal,
    TerminalButton,
    TerminalConfig,
    TerminalRegistrationSuccess,
    TerminalSecrets,
    TerminalTillConfig,
    UserTagSecret,
)
from stustapay.core.schema.till import TillProfile
from stustapay.core.schema.tree import Node, ObjectType
from stustapay.core.schema.user import Privilege
from stustapay.core.service.auth import AuthService, TerminalTokenMetadata
from stustapay.core.service.common.dbservice import DBService
from stustapay.core.service.common.decorators import (
    requires_node,
    requires_terminal,
    requires_user,
    with_db_transaction,
    with_retryable_db_transaction,
)
from stustapay.core.service.common.error import AccessDenied, NotFound
from stustapay.core.service.tree.common import fetch_restricted_event_settings_for_node
from stustapay.core.service.user import list_user_roles
from stustapay.framework.database import Connection


async def _fetch_terminal(conn: Connection, node: Node, terminal_id: int) -> Terminal | None:
    return await conn.fetch_maybe_one(
        Terminal,
        "select t.*, till.id as till_id from terminal t left join till on t.id = till.terminal_id "
        "where t.id = $1 and t.node_id = any($2)",
        terminal_id,
        node.ids_to_root,
    )


class TerminalService(DBService):
    def __init__(self, db_pool: asyncpg.Pool, config: Config, auth_service: AuthService):
        super().__init__(db_pool, config)
        self.auth_service = auth_service

    @with_db_transaction
    @requires_node(object_types=[ObjectType.terminal])
    @requires_user([Privilege.node_administration])
    async def create_terminal(self, *, conn: Connection, node: Node, terminal: NewTerminal) -> Terminal:
        terminal_id = await conn.fetchval(
            "insert into terminal (node_id, name, description) values ($1, $2, $3) returning id",
            node.id,
            terminal.name,
            terminal.description,
        )
        t = await _fetch_terminal(conn=conn, node=node, terminal_id=terminal_id)
        assert t is not None
        return t

    @with_db_transaction(read_only=True)
    @requires_node()
    @requires_user([Privilege.node_administration])
    async def list_terminals(self, *, conn: Connection, node: Node) -> list[Terminal]:
        return await conn.fetch_many(
            Terminal,
            "select t.*, till.id as till_id from terminal t left join till on t.id = till.terminal_id "
            "where t.node_id = any($1) order by t.name",
            node.ids_to_root,
        )

    @with_db_transaction(read_only=True)
    @requires_node()
    @requires_user([Privilege.node_administration])
    async def get_terminal(self, *, conn: Connection, node: Node, terminal_id: int) -> Optional[Terminal]:
        return await _fetch_terminal(conn=conn, node=node, terminal_id=terminal_id)

    @with_db_transaction
    @requires_node(object_types=[ObjectType.terminal])
    @requires_user([Privilege.node_administration])
    async def update_terminal(
        self, *, conn: Connection, node: Node, terminal_id: int, terminal: NewTerminal
    ) -> Terminal:
        term_id = await conn.fetchval(
            "update terminal set name = $1, description = $2 where id = $3 and node_id = $4 returning id",
            terminal.name,
            terminal.description,
            terminal_id,
            node.id,
        )
        if term_id is None:
            raise NotFound(element_typ="terminal", element_id=terminal_id)
        updated_terminal = await _fetch_terminal(conn=conn, node=node, terminal_id=terminal_id)
        assert updated_terminal is not None
        return updated_terminal

    @with_db_transaction
    @requires_node(object_types=[ObjectType.terminal])
    @requires_user([Privilege.node_administration])
    async def delete_terminal(self, *, conn: Connection, node: Node, terminal_id: int) -> bool:
        result = await conn.execute("delete from terminal where id = $1 and node_id = $2", terminal_id, node.id)
        return result != "DELETE 0"

    @with_retryable_db_transaction(read_only=False)
    async def register_terminal(self, *, conn: Connection, registration_uuid: str) -> TerminalRegistrationSuccess:
        # TODO: TREE visibility
        terminal = await conn.fetch_maybe_one(
            Terminal,
            "select t.*, till.id as till_id "
            "from terminal t "
            "left join till on t.id = till.terminal_id "
            "where registration_uuid = $1",
            registration_uuid,
        )
        if terminal is None:
            raise AccessDenied("Invalid registration uuid")

        session_uuid = await conn.fetchval(
            "update terminal set session_uuid = gen_random_uuid(), registration_uuid = null where id = $1 "
            "returning session_uuid",
            terminal.id,
        )
        token = self.auth_service.create_terminal_access_token(
            TerminalTokenMetadata(terminal_id=terminal.id, session_uuid=session_uuid)
        )
        return TerminalRegistrationSuccess(terminal=terminal, token=token)

    @with_db_transaction
    @requires_node(object_types=[ObjectType.terminal])
    @requires_user([Privilege.node_administration])
    async def logout_terminal_id(self, *, conn: Connection, node: Node, terminal_id: int) -> bool:
        # TODO: TREE visibility
        id_ = await conn.fetchval(
            "update terminal set registration_uuid = gen_random_uuid(), session_uuid = null "
            "where id = $1 and node_id = $2 returning id",
            terminal_id,
            node.id,
        )
        if id_ is None:
            raise NotFound(element_typ="terminal", element_id=terminal_id)
        await conn.execute("update till set terminal_id = null where terminal_id = $1", terminal_id)
        return True

    @with_db_transaction
    @requires_terminal()
    async def logout_terminal(self, *, conn: Connection, current_terminal: CurrentTerminal):
        await conn.fetchval(
            "update terminal set registration_uuid = gen_random_uuid(), session_uuid = null where id = $1",
            current_terminal.id,
        )
        await conn.execute("update till set terminal_id = null where terminal_id = $1", current_terminal.id)

    @with_db_transaction(read_only=True)
    @requires_terminal()
    async def get_terminal_config(
        self, *, conn: Connection, current_terminal: CurrentTerminal, node: Node
    ) -> TerminalConfig | None:
        event_settings = await fetch_restricted_event_settings_for_node(conn=conn, node_id=node.id)
        profile = await conn.fetch_one(
            TillProfile,
            "select * from till_profile tp where id = $1",
            current_terminal.till.active_profile_id,
        )
        layout_has_tickets = await conn.fetchval(
            "select exists (select from till_layout_to_ticket tltt where layout_id = $1)",
            profile.layout_id,
        )
        allow_ticket_sale = layout_has_tickets and profile.allow_ticket_sale

        user_privileges = await conn.fetchval(
            "select privileges from user_with_privileges where id = $1",
            current_terminal.till.active_user_id,
        )
        buttons = await conn.fetch_many(
            TerminalButton,
            "select tlwb.* "
            "from till_button_with_products tlwb "
            "join till_layout_to_button tltb on tltb.button_id = tlwb.id "
            "where tltb.layout_id = $1 "
            "order by tltb.sequence_number asc",
            profile.layout_id,
        )

        cash_register_id = None
        cash_register_name = None
        cash_reg = await conn.fetchrow(
            "select cr.id, cr.name "
            "from cash_register cr "
            "join till t on cr.id = t.active_cash_register_id "
            "where t.id = $1",
            current_terminal.till.id,
        )
        if cash_reg is not None:
            cash_register_id = cash_reg["id"]
            cash_register_name = cash_reg["name"]

        # TODO: tree, fetch correct secret
        user_tag_secret = await conn.fetch_one(
            UserTagSecret,
            "select encode(key0, 'hex') as key0, encode(key1, 'hex') as key1 from user_tag_secret limit 1",
        )
        sumup_key = ""
        if profile.allow_ticket_sale or profile.allow_top_up:
            sumup_key = event_settings.sumup_affiliate_key

        secrets = TerminalSecrets(sumup_affiliate_key=sumup_key, user_tag_secret=user_tag_secret)

        available_roles = await list_user_roles(conn=conn, node=node)

        return TerminalConfig(
            id=current_terminal.id,
            name=current_terminal.name,
            description=current_terminal.description,
            till=TerminalTillConfig(
                id=current_terminal.till.id,
                name=current_terminal.till.name,
                description=current_terminal.till.description,
                cash_register_id=cash_register_id,
                cash_register_name=cash_register_name,
                user_privileges=user_privileges,
                profile_name=profile.name,
                allow_top_up=profile.allow_top_up,
                allow_cash_out=profile.allow_cash_out,
                allow_ticket_sale=allow_ticket_sale,
                buttons=buttons,
                secrets=secrets,
                available_roles=available_roles,
                active_user_id=current_terminal.till.active_user_id,
            ),
            test_mode=self.cfg.core.test_mode,
            test_mode_message=self.cfg.core.test_mode_message,
        )
