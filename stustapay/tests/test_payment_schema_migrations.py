import pytest
from sftkit.database import Connection
from sftkit.database._migrations import MIGRATION_TABLE, SchemaMigration

from stustapay.core.database import CURRENT_REVISION
from stustapay.core.schema import MIGRATION_PATH


@pytest.mark.parametrize("upgrade_state", ["complete", "missing", "legacy_terminal"])
async def test_payment_schema_upgrade_from_released_revision(db_connection: Connection, upgrade_state: str):
    migrations = SchemaMigration.migrations_from_dir(MIGRATION_PATH)
    released_index = next(i for i, migration in enumerate(migrations) if migration.version == "a6f94d21")
    assert migrations[released_index].requires == "13c7b823"
    assert [m.version for m in migrations[released_index + 1 : released_index + 4]] == [
        "92f445c4",
        "d4a7c9e1",
        "7f3e9b21",
    ]

    # Keep destructive schema setup inside a transaction that is always rolled back.
    transaction = db_connection.transaction()
    await transaction.start()
    try:
        await db_connection.execute("drop schema public cascade; create schema public")
        await db_connection.execute(f"create table {MIGRATION_TABLE} (version text not null primary key)")
        for migration in migrations[: released_index + 1]:
            await migration.apply(db_connection)
        await db_connection.execute(
            "insert into node_sumup_link (node_id, merchant_code, refresh_token) values (0, 'merchant', 'test-refresh')"
        )
        terminal_id = await db_connection.fetchval(
            "insert into terminal (node_id, name) values (1, 'Migration test terminal') returning id"
        )
        await db_connection.execute("update till set terminal_id = $1 where id = 1", terminal_id)
        for migration in migrations[released_index + 1 :]:
            if upgrade_state != "complete" and migration.version in ("92f445c4", "d4a7c9e1", "7f3e9b21"):
                # Reproduce an already-upgraded branch database with the missing payment schema.
                if upgrade_state == "legacy_terminal" and migration.version == "92f445c4":
                    await db_connection.execute(
                        "alter table terminal add column tap_to_pay_enabled boolean not null default false"
                    )
                    await db_connection.execute(
                        "update terminal set tap_to_pay_enabled = true where id = $1", terminal_id
                    )
                await db_connection.execute(f"update {MIGRATION_TABLE} set version = $1", migration.version)
            else:
                await migration.apply(db_connection)
                if migration.version == "92f445c4":
                    await db_connection.execute(
                        "update terminal set tap_to_pay_enabled = true where id = $1", terminal_id
                    )

        assert await db_connection.fetchval(f"select version from {MIGRATION_TABLE}") == CURRENT_REVISION
        existing_terminal = await db_connection.fetchrow(
            "select login_mode::text, device_user_id, active_user_id from terminal where id = $1", terminal_id
        )
        assert existing_terminal["login_mode"] == "personal"
        assert existing_terminal["device_user_id"] is None
        assert existing_terminal["active_user_id"] is None
        columns = await db_connection.fetch(
            "select table_name, column_name from information_schema.columns where table_schema = 'public'"
        )
        column_names = {(row["table_name"], row["column_name"]) for row in columns}
        assert {
            ("event", "tap_to_pay_enabled"),
            ("till_profile", "tap_to_pay_enabled"),
            ("event", "sumup_environment"),
            ("pending_sumup_order", "sumup_environment"),
            ("node_sumup_link", "environment"),
            ("node_sumup_link", "auth_method"),
            ("node_sumup_link", "api_key"),
        } <= column_names
        assert ("terminal", "tap_to_pay_enabled") not in column_names
        assert await db_connection.fetchval("select tap_to_pay_enabled from till_profile where id = 1") == (
            upgrade_state != "missing"
        )
        link = await db_connection.fetchrow(
            "select refresh_token, environment::text, auth_method::text from node_sumup_link where node_id = 0"
        )
        assert link["refresh_token"] == "test-refresh"
        assert link["environment"] == "live"
        assert link["auth_method"] == "oauth"
        # The repaired primary key supports separate live and sandbox credentials.
        await db_connection.execute(
            "insert into node_sumup_link (node_id, merchant_code, environment, auth_method, api_key) "
            "values (0, 'sandbox-merchant', 'sandbox', 'api_key', 'test-api-key')"
        )
    finally:
        await transaction.rollback()
