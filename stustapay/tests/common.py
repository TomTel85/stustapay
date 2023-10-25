# pylint: disable=attribute-defined-outside-init,unexpected-keyword-arg,missing-kwoa
import asyncio
import logging
import os
import tempfile
from pathlib import Path
from unittest import IsolatedAsyncioTestCase as TestCase

from asyncpg.pool import Pool

from stustapay.core import database
from stustapay.core.config import (
    AdministrationApiConfig,
    BonConfig,
    Config,
    CoreConfig,
    CustomerPortalApiConfig,
    DatabaseConfig,
    TerminalApiConfig,
)
from stustapay.core.schema.account import AccountType
from stustapay.core.schema.product import NewProduct
from stustapay.core.schema.tax_rate import NewTaxRate
from stustapay.core.schema.till import (
    NewCashRegister,
    NewCashRegisterStocking,
    NewTill,
    NewTillButton,
    NewTillLayout,
    NewTillProfile,
)
from stustapay.core.schema.user import (
    ADMIN_ROLE_ID,
    ADMIN_ROLE_NAME,
    CASHIER_ROLE_ID,
    CASHIER_ROLE_NAME,
    FINANZORGA_ROLE_NAME,
    NewUser,
    UserTag,
)
from stustapay.core.service.account import AccountService, get_system_account_for_node
from stustapay.core.service.auth import AuthService
from stustapay.core.service.config import ConfigService
from stustapay.core.service.product import ProductService
from stustapay.core.service.tax_rate import TaxRateService, fetch_tax_rate_none
from stustapay.core.service.till import TillService
from stustapay.core.service.tree.common import fetch_event_node_for_node
from stustapay.core.service.user import UserService
from stustapay.core.service.user_tag import UserTagService
from stustapay.framework.database import Connection, create_db_pool


def get_test_db_config() -> DatabaseConfig:
    return DatabaseConfig(
        user=os.environ.get("TEST_DB_USER", None),
        password=os.environ.get("TEST_DB_PASSWORD", None),
        host=os.environ.get("TEST_DB_HOST", None),
        port=int(os.environ.get("TEST_DB_PORT", 0)) or None,
        dbname=os.environ.get("TEST_DB_DATABASE", "stustapay_test"),
    )


# input structure for core.config.Config
TEST_CONFIG = Config(
    core=CoreConfig(secret_key="stuff1234"),
    administration=AdministrationApiConfig(
        base_url="http://localhost:8081",
        host="localhost",
        port=8081,
    ),
    terminalserver=TerminalApiConfig(
        base_url="http://localhost:8080",
        host="localhost",
        port=8080,
    ),
    customer_portal=CustomerPortalApiConfig(
        base_url="http://localhost:8082",
        base_bon_url="https://bon.stustapay.de/{bon_output_file}",
        data_privacy_url="https://stustapay.de/datenschutz",
        about_page_url="https://stustapay.de/impressum",
    ),
    bon=BonConfig(output_folder=Path("tmp")),
    database=get_test_db_config(),
)


async def get_test_db() -> Pool:
    """
    get a connection pool to the test database
    """
    cfg = get_test_db_config()
    pool = await create_db_pool(cfg=cfg)

    await database.reset_schema(pool)
    await database.apply_revisions(pool)

    return pool


testing_lock = asyncio.Lock()


class BaseTestCase(TestCase):
    def __init__(self, *args, log_level=logging.DEBUG, **kwargs):
        super().__init__(*args, **kwargs)
        logging.basicConfig(level=log_level)

    async def asyncSetUp(self) -> None:
        await testing_lock.acquire()
        self.db_pool = await get_test_db()
        self.db_conn: Connection = await self.db_pool.acquire()

        self.node_id = 1
        event_node = await fetch_event_node_for_node(conn=self.db_conn, node_id=self.node_id)
        assert event_node is not None
        assert event_node.event is not None
        self.node = event_node
        self.event = event_node.event

        await self.db_conn.execute(
            "insert into user_tag_secret (node_id, id, key0, key1) overriding system value values "
            "($1, 0, decode('000102030405060708090a0b0c0d0e0f', 'hex'), decode('000102030405060708090a0b0c0d0e0f', 'hex')) "
            "on conflict do nothing",
            self.node_id,
        )

        self.test_config = Config.model_validate(TEST_CONFIG)

        self.auth_service = AuthService(db_pool=self.db_pool, config=self.test_config)
        self.user_service = UserService(db_pool=self.db_pool, config=self.test_config, auth_service=self.auth_service)
        self.account_service = AccountService(
            db_pool=self.db_pool, config=self.test_config, auth_service=self.auth_service
        )
        self.config_service = ConfigService(
            db_pool=self.db_pool, config=self.test_config, auth_service=self.auth_service
        )
        self.user_tag_service = UserTagService(
            db_pool=self.db_pool, config=self.test_config, auth_service=self.auth_service
        )
        self.till_service = TillService(
            db_pool=self.db_pool,
            config=self.test_config,
            auth_service=self.auth_service,
        )
        self.tax_rate_service = TaxRateService(
            db_pool=self.db_pool,
            config=self.test_config,
            auth_service=self.auth_service,
        )

        self.admin_tag_uid = await self.db_conn.fetchval(
            "insert into user_tag (node_id, uid) values ($1, 13131313) returning uid", self.node_id
        )
        self.admin_user = await self.user_service.create_user_no_auth(
            node_id=self.node_id,
            new_user=NewUser(
                login="test-admin-user",
                description="",
                role_names=[ADMIN_ROLE_NAME],
                display_name="Admin",
                user_tag_uid=self.admin_tag_uid,
            ),
            password="rolf",
        )
        self.admin_token = (await self.user_service.login_user(username=self.admin_user.login, password="rolf")).token
        # TODO: tree, this has to be replaced as soon as we have proper tree visibility rules
        self.global_admin_token = self.admin_token
        self.finanzorga_tag_uid = await self.db_conn.fetchval(
            "insert into user_tag (node_id, uid) values ($1, 1313131313) returning uid", self.node_id
        )
        self.finanzorga_user = await self.user_service.create_user_no_auth(
            node_id=self.node_id,
            new_user=NewUser(
                login="test-finanzorga-user",
                description="",
                role_names=[FINANZORGA_ROLE_NAME],
                display_name="Finanzorga",
                user_tag_uid=self.finanzorga_tag_uid,
            ),
            password="rolf",
        )
        self.cashier_tag_uid = await self.db_conn.fetchval(
            "insert into user_tag (node_id, uid) values ($1, 54321) returning uid", self.node_id
        )
        self.cashier = await self.user_service.create_user_no_auth(
            node_id=self.node_id,
            new_user=NewUser(
                login="test-cashier-user",
                user_tag_uid=self.cashier_tag_uid,
                description="",
                role_names=[],
                display_name="Cashier",
            ),
            password="rolf",
        )
        await self.user_service.promote_to_cashier(token=self.admin_token, user_id=self.cashier.id)
        self.cashier = await self.user_service.get_user(token=self.admin_token, user_id=self.cashier.id)

        self.cashier_token = (await self.user_service.login_user(username=self.cashier.login, password="rolf")).token

        self.tax_rate_none = await fetch_tax_rate_none(conn=self.db_conn, node=event_node)
        self.tax_rate_ust = await self.tax_rate_service.create_tax_rate(
            token=self.admin_token, node_id=self.node_id, tax_rate=NewTaxRate(name="ust", description="", rate=0.19)
        )

        # create tmp folder for tests which handle files
        self.tmp_dir_obj = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self.tmp_dir_obj.name)

    async def _get_account_balance(self, account_id: int) -> float:
        account = await self.account_service.get_account(token=self.admin_token, account_id=account_id)
        self.assertIsNotNone(account)
        return account.balance

    async def _assert_account_balance(self, account_id: int, expected_balance: float):
        balance = await self._get_account_balance(account_id=account_id)
        self.assertEqual(expected_balance, balance)

    async def _get_system_account_balance(self, account_type: AccountType):
        account = await get_system_account_for_node(conn=self.db_conn, node=self.node, account_type=account_type)
        return account.balance

    async def _assert_system_account_balance(self, account_type: AccountType, expected_balance: float):
        balance = await self._get_system_account_balance(account_type=account_type)
        self.assertEqual(expected_balance, balance)

    async def asyncTearDown(self) -> None:
        await self.db_conn.close()
        await self.db_pool.close()

        testing_lock.release()

        # delete tmp folder for tests which handle files with all its content
        self.tmp_dir_obj.cleanup()


class TerminalTestCase(BaseTestCase):
    async def _login_supervised_user(self, user_tag_uid: int, user_role_id: int):
        await self.till_service.logout_user(token=self.terminal_token)
        await self.till_service.login_user(
            token=self.terminal_token, user_tag=UserTag(uid=self.admin_tag_uid), user_role_id=ADMIN_ROLE_ID
        )
        await self.till_service.login_user(
            token=self.terminal_token, user_tag=UserTag(uid=user_tag_uid), user_role_id=user_role_id
        )

    async def create_terminal(self, name: str) -> str:
        till = await self.till_service.create_till(
            token=self.admin_token,
            till=NewTill(
                name=name,
                active_profile_id=self.till_profile.id,
            ),
        )
        return (await self.till_service.register_terminal(registration_uuid=till.registration_uuid)).token

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()

        self.customer_tag_uid = int(
            await self.db_conn.fetchval(
                "insert into user_tag (node_id, uid) values ($1, $2) returning uid", self.node_id, 12345676
            )
        )
        await self.db_conn.execute(
            "insert into account (node_id, user_tag_uid, type, balance) values ($1, $2, $3, 100)",
            self.node_id,
            self.customer_tag_uid,
            AccountType.private.name,
        )

        self.product_service = ProductService(
            db_pool=self.db_pool, config=self.test_config, auth_service=self.auth_service
        )
        self.product = await self.product_service.create_product(
            token=self.admin_token,
            node_id=self.node_id,
            product=NewProduct(
                name="Helles",
                price=3,
                tax_rate_id=self.tax_rate_ust.id,
                is_locked=True,
                fixed_price=True,
                restrictions=[],
                is_returnable=False,
            ),
        )
        self.till_button = await self.till_service.layout.create_button(
            token=self.admin_token, button=NewTillButton(name="Helles", product_ids=[self.product.id])
        )
        self.till_layout = await self.till_service.layout.create_layout(
            token=self.admin_token,
            node_id=self.node_id,
            layout=NewTillLayout(name="test-layout", description="", button_ids=[self.till_button.id]),
        )
        self.till_profile = await self.till_service.profile.create_profile(
            token=self.admin_token,
            node_id=self.node_id,
            profile=NewTillProfile(
                name="test-profile",
                description="",
                layout_id=self.till_layout.id,
                allow_top_up=True,
                allow_cash_out=True,
                allow_ticket_sale=True,
                allowed_role_names=[ADMIN_ROLE_NAME, FINANZORGA_ROLE_NAME, CASHIER_ROLE_NAME],
            ),
        )
        self.till = await self.till_service.create_till(
            token=self.admin_token,
            node_id=self.node_id,
            till=NewTill(
                name="test-till",
                active_profile_id=self.till_profile.id,
            ),
        )
        self.terminal_token = (
            await self.till_service.register_terminal(registration_uuid=self.till.registration_uuid)
        ).token
        self.register = await self.till_service.register.create_cash_register(
            node_id=self.node_id, token=self.admin_token, new_register=NewCashRegister(name="Lade")
        )
        await self._login_supervised_user(user_tag_uid=self.admin_tag_uid, user_role_id=ADMIN_ROLE_ID)
        self.stocking = await self.till_service.register.create_cash_register_stockings(
            node_id=self.node_id,
            token=self.admin_token,
            stocking=NewCashRegisterStocking(name="My fancy stocking"),
        )
        await self.till_service.register.stock_up_cash_register(
            token=self.terminal_token,
            cashier_tag_uid=self.cashier_tag_uid,
            stocking_id=self.stocking.id,
            cash_register_id=self.register.id,
        )
        # log in the cashier user
        await self._login_supervised_user(user_tag_uid=self.cashier_tag_uid, user_role_id=CASHIER_ROLE_ID)
