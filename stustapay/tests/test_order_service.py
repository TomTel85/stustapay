# pylint: disable=attribute-defined-outside-init,unexpected-keyword-arg,missing-kwoa
import uuid

from stustapay.core.schema.account import (
    ACCOUNT_SALE_EXIT,
    ACCOUNT_CASH_VAULT,
    ACCOUNT_CASH_ENTRY,
    ACCOUNT_SUMUP,
    ACCOUNT_CASH_EXIT,
)
from stustapay.core.schema.order import (
    NewSale,
    Button,
    NewTopUp,
    PaymentMethod,
    NewPayOut,
    Order,
    NewTicketSale,
    PendingTicketSale,
)
from stustapay.core.schema.product import NewProduct
from stustapay.core.schema.till import NewTill, NewTillLayout, NewTillProfile, NewTillButton
from stustapay.core.service.account import AccountService
from stustapay.core.service.order import OrderService, NotEnoughVouchersException
from stustapay.core.service.order.order import NotEnoughFundsException
from stustapay.core.service.order.order import TillPermissionException, InvalidSaleException
from stustapay.core.service.product import ProductService
from stustapay.core.service.till import TillService
from .common import TerminalTestCase
from ..core.schema.user import ADMIN_ROLE_NAME, FINANZORGA_ROLE_NAME, CASHIER_ROLE_NAME

START_BALANCE = 100


class OrderLogicTest(TerminalTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.product_service = ProductService(
            db_pool=self.db_pool, config=self.test_config, auth_service=self.auth_service
        )
        self.till_service = TillService(db_pool=self.db_pool, config=self.test_config, auth_service=self.auth_service)
        self.account_service = AccountService(
            db_pool=self.db_pool, config=self.test_config, auth_service=self.auth_service
        )
        self.order_service = OrderService(
            db_pool=self.db_pool,
            config=self.test_config,
            auth_service=self.auth_service,
        )

        self.beer_product = await self.product_service.create_product(
            token=self.admin_token,
            product=NewProduct(
                name="Helles 0,5l",
                price=3,
                fixed_price=True,
                tax_name="ust",
                target_account_id=None,
                price_in_vouchers=1,
                is_locked=True,
            ),
        )
        self.deposit_product = await self.product_service.create_product(
            token=self.admin_token,
            product=NewProduct(
                name="Pfand",
                price=2,
                fixed_price=True,
                tax_name="none",
                target_account_id=None,
                is_locked=True,
                is_returnable=True,
            ),
        )
        self.beer_button = await self.till_service.layout.create_button(
            token=self.admin_token,
            button=NewTillButton(name="Helles 0,5l", product_ids=[self.beer_product.id, self.deposit_product.id]),
        )
        self.deposit_button = await self.till_service.layout.create_button(
            token=self.admin_token,
            button=NewTillButton(name="Pfand", product_ids=[self.deposit_product.id]),
        )
        self.till_layout = await self.till_service.layout.create_layout(
            token=self.admin_token,
            layout=NewTillLayout(name="layout1", description="", button_ids=None),
        )
        self.till_profile = await self.till_service.profile.create_profile(
            token=self.admin_token,
            profile=NewTillProfile(
                name="profile1",
                description="",
                layout_id=self.till_layout.id,
                allow_top_up=True,
                allow_cash_out=True,
                allow_ticket_sale=True,
                allowed_role_names=[ADMIN_ROLE_NAME, FINANZORGA_ROLE_NAME, CASHIER_ROLE_NAME],
            ),
        )
        self.till = await self.till_service.update_till(
            token=self.admin_token,
            till_id=self.till.id,
            till=NewTill(
                name="test-till",
                active_profile_id=self.till_profile.id,
            ),
        )
        # add customer
        self.customer_uid = await self.db_conn.fetchval("insert into user_tag (uid) values (1234) returning uid")
        self.customer_account_id = await self.db_conn.fetchval(
            "insert into account (user_tag_uid, type, balance) values ($1, 'private', $2) returning id",
            self.customer_uid,
            START_BALANCE,
        )
        self.unused_tag_uid = await self.db_conn.fetchval("insert into user_tag (uid) values (12345) returning uid")

        self.ticket_price = 12  # TODO: remove ugly hardcoding

    async def _assert_account_balance(self, account_id: int, balance: float):
        account = await self.account_service.get_account(token=self.admin_token, account_id=account_id)
        self.assertIsNotNone(account)
        self.assertEqual(balance, account.balance)

    async def test_basic_sale_flow(self):
        customer_acc = await self.till_service.get_customer(
            token=self.terminal_token, customer_tag_uid=self.customer_uid
        )
        self.assertIsNotNone(customer_acc)
        starting_balance = customer_acc.balance
        new_sale = NewSale(
            buttons=[Button(till_button_id=self.beer_button.id, quantity=2)],
            customer_tag_uid=self.customer_uid,
        )
        pending_sale = await self.order_service.check_sale(
            token=self.terminal_token,
            new_sale=new_sale,
        )
        self.assertEqual(pending_sale.old_balance, START_BALANCE)
        self.assertEqual(pending_sale.item_count, 2)
        self.assertEqual(len(pending_sale.line_items), 2)
        self.assertEqual(pending_sale.total_price, 2 * self.beer_product.price + 2 * self.deposit_product.price)
        self.assertEqual(pending_sale.new_balance, START_BALANCE - pending_sale.total_price)
        completed_sale = await self.order_service.book_sale(token=self.terminal_token, new_sale=new_sale)
        self.assertIsNotNone(completed_sale)
        order: Order = await self.order_service.get_order(token=self.admin_token, order_id=completed_sale.id)
        self.assertIsNotNone(order)
        await self._assert_account_balance(account_id=ACCOUNT_SALE_EXIT, balance=order.total_price)

        # test that we can cancel this order
        success = await self.order_service.cancel_sale(token=self.terminal_token, order_id=order.id)
        self.assertTrue(success)
        customer = await self.till_service.get_customer(token=self.terminal_token, customer_tag_uid=self.customer_uid)
        self.assertIsNotNone(customer)
        self.assertEqual(starting_balance, customer.balance)
        await self._assert_account_balance(account_id=ACCOUNT_SALE_EXIT, balance=0)

    async def test_returnable_products(self):
        new_sale = NewSale(
            buttons=[Button(till_button_id=self.beer_button.id, quantity=-1)],
            customer_tag_uid=self.customer_uid,
        )
        with self.assertRaises(InvalidSaleException):
            await self.order_service.check_sale(
                token=self.terminal_token,
                new_sale=new_sale,
            )

        new_sale = NewSale(
            buttons=[Button(till_button_id=self.deposit_button.id, quantity=-1)],
            customer_tag_uid=self.customer_uid,
        )
        pending_sale = await self.order_service.check_sale(
            token=self.terminal_token,
            new_sale=new_sale,
        )
        self.assertEqual(pending_sale.total_price, -self.deposit_product.price)

    async def test_basic_sale_flow_with_deposit(self):
        new_sale = NewSale(
            buttons=[
                Button(till_button_id=self.beer_button.id, quantity=3),
                Button(till_button_id=self.beer_button.id, quantity=2),
                Button(till_button_id=self.deposit_button.id, quantity=-1),
                Button(till_button_id=self.deposit_button.id, quantity=-1),
                Button(till_button_id=self.deposit_button.id, quantity=-2),
            ],
            customer_tag_uid=self.customer_uid,
        )
        pending_sale = await self.order_service.check_sale(
            token=self.terminal_token,
            new_sale=new_sale,
        )
        self.assertEqual(pending_sale.old_balance, START_BALANCE)
        # our initial order gets aggregated into one line item for beer and one for deposit
        self.assertEqual(len(pending_sale.line_items), 2)
        self.assertEqual(pending_sale.total_price, 5 * self.beer_product.price + self.deposit_product.price)
        self.assertEqual(pending_sale.new_balance, START_BALANCE - pending_sale.total_price)
        completed_sale = await self.order_service.book_sale(token=self.terminal_token, new_sale=new_sale)
        self.assertIsNotNone(completed_sale)

    async def test_basic_sale_flow_with_only_deposit_return(self):
        new_sale = NewSale(
            buttons=[
                Button(till_button_id=self.deposit_button.id, quantity=-1),
                Button(till_button_id=self.deposit_button.id, quantity=-2),
            ],
            customer_tag_uid=self.customer_uid,
        )
        pending_sale = await self.order_service.check_sale(
            token=self.terminal_token,
            new_sale=new_sale,
        )
        self.assertEqual(pending_sale.old_balance, START_BALANCE)
        # our initial order gets aggregated into one line item for beer and one for deposit
        self.assertEqual(len(pending_sale.line_items), 1)
        self.assertEqual(pending_sale.total_price, -3 * self.deposit_product.price)
        self.assertEqual(pending_sale.new_balance, START_BALANCE - pending_sale.total_price)
        completed_sale = await self.order_service.book_sale(token=self.terminal_token, new_sale=new_sale)
        self.assertIsNotNone(completed_sale)

    async def test_basic_sale_flow_with_vouchers(self):
        await self.db_conn.execute("update account set vouchers = 3 where id = $1", self.customer_account_id)
        new_sale = NewSale(
            buttons=[
                Button(till_button_id=self.beer_button.id, quantity=3),
            ],
            customer_tag_uid=self.customer_uid,
        )
        pending_sale = await self.order_service.check_sale(
            token=self.terminal_token,
            new_sale=new_sale,
        )
        self.assertEqual(pending_sale.old_balance, 100)
        self.assertEqual(pending_sale.new_balance, 100 - self.deposit_product.price * 3)
        self.assertEqual(pending_sale.item_count, 3)  # rabatt + bier + pfand
        self.assertEqual(len(pending_sale.line_items), 3)
        self.assertEqual(pending_sale.old_voucher_balance, 3)
        self.assertEqual(pending_sale.new_voucher_balance, 0)
        completed_sale = await self.order_service.book_sale(token=self.terminal_token, new_sale=new_sale)
        self.assertIsNotNone(completed_sale)

    async def test_basic_sale_flow_with_fixed_vouchers(self):
        await self.db_conn.execute("update account set vouchers = 3 where id = $1", self.customer_account_id)
        new_sale = NewSale(
            buttons=[
                Button(till_button_id=self.beer_button.id, quantity=3),
            ],
            customer_tag_uid=self.customer_uid,
            used_vouchers=4,
        )
        with self.assertRaises(NotEnoughVouchersException):
            await self.order_service.check_sale(
                token=self.terminal_token,
                new_sale=new_sale,
            )
        new_sale.used_vouchers = 2
        pending_sale = await self.order_service.check_sale(
            token=self.terminal_token,
            new_sale=new_sale,
        )
        self.assertEqual(pending_sale.old_voucher_balance, 3)
        self.assertEqual(pending_sale.new_voucher_balance, 1)
        completed_sale = await self.order_service.book_sale(token=self.terminal_token, new_sale=new_sale)
        self.assertIsNotNone(completed_sale)

    async def test_only_topup_till_profiles_can_topup(self):
        profile = await self.till_service.profile.create_profile(
            token=self.admin_token,
            profile=NewTillProfile(
                name="profile2",
                description="",
                layout_id=self.till_layout.id,
                allow_top_up=False,
                allow_cash_out=False,
                allow_ticket_sale=False,
                allowed_role_names=[ADMIN_ROLE_NAME, FINANZORGA_ROLE_NAME, CASHIER_ROLE_NAME],
            ),
        )
        self.till.active_profile_id = profile.id
        await self.till_service.update_till(token=self.admin_token, till_id=self.till.id, till=self.till)

        with self.assertRaises(TillPermissionException):
            new_topup = NewTopUp(
                amount=20,
                payment_method=PaymentMethod.cash,
                customer_tag_uid=self.customer_uid,
            )
            await self.order_service.check_topup(token=self.terminal_token, new_topup=new_topup)

    async def test_topup_cash_order_flow(self):
        new_topup = NewTopUp(
            amount=20,
            payment_method=PaymentMethod.cash,
            customer_tag_uid=self.customer_uid,
        )
        pending_top_up = await self.order_service.check_topup(token=self.terminal_token, new_topup=new_topup)
        self.assertEqual(pending_top_up.old_balance, START_BALANCE)
        self.assertEqual(pending_top_up.amount, 20)
        self.assertEqual(pending_top_up.new_balance, START_BALANCE + pending_top_up.amount)
        completed_topup = await self.order_service.book_topup(token=self.terminal_token, new_topup=new_topup)
        self.assertIsNotNone(completed_topup)
        self.assertEqual(completed_topup.old_balance, START_BALANCE)
        self.assertEqual(completed_topup.amount, 20)
        self.assertEqual(completed_topup.new_balance, START_BALANCE + completed_topup.amount)
        await self._assert_account_balance(account_id=self.cashier.cashier_account_id, balance=20)
        await self._assert_account_balance(account_id=ACCOUNT_CASH_ENTRY, balance=-20)
        await self._assert_account_balance(account_id=ACCOUNT_CASH_VAULT, balance=-20)

    async def test_topup_sumup_order_flow(self):
        new_topup = NewTopUp(
            uuid=uuid.uuid4(),
            amount=20,
            payment_method=PaymentMethod.sumup,
            customer_tag_uid=self.customer_uid,
        )
        pending_topup = await self.order_service.check_topup(
            token=self.terminal_token,
            new_topup=new_topup,
        )
        self.assertEqual(pending_topup.old_balance, START_BALANCE)
        self.assertEqual(pending_topup.amount, 20)
        self.assertEqual(pending_topup.new_balance, START_BALANCE + pending_topup.amount)
        completed_topup = await self.order_service.book_topup(token=self.terminal_token, new_topup=new_topup)
        self.assertIsNotNone(completed_topup)
        self.assertEqual(completed_topup.uuid, new_topup.uuid)
        self.assertEqual(completed_topup.old_balance, START_BALANCE)
        self.assertEqual(completed_topup.amount, 20)
        self.assertEqual(completed_topup.new_balance, START_BALANCE + completed_topup.amount)
        await self._assert_account_balance(account_id=ACCOUNT_SUMUP, balance=-20)

    async def test_only_payout_till_profiles_can_payout(self):
        profile = await self.till_service.profile.create_profile(
            token=self.admin_token,
            profile=NewTillProfile(
                name="profile2",
                description="",
                layout_id=self.till_layout.id,
                allow_top_up=False,
                allow_cash_out=False,
                allow_ticket_sale=False,
                allowed_role_names=[ADMIN_ROLE_NAME, FINANZORGA_ROLE_NAME, CASHIER_ROLE_NAME],
            ),
        )
        self.till.active_profile_id = profile.id
        await self.till_service.update_till(token=self.admin_token, till_id=self.till.id, till=self.till)

        with self.assertRaises(TillPermissionException):
            new_pay_out = NewPayOut(
                customer_tag_uid=self.customer_uid,
            )
            await self.order_service.check_pay_out(token=self.terminal_token, new_pay_out=new_pay_out)

    async def test_cash_pay_out_flow_no_amount(self):
        new_pay_out = NewPayOut(customer_tag_uid=self.customer_uid)
        pending_pay_out = await self.order_service.check_pay_out(token=self.terminal_token, new_pay_out=new_pay_out)
        self.assertEqual(pending_pay_out.old_balance, START_BALANCE)
        self.assertEqual(pending_pay_out.new_balance, 0)
        self.assertEqual(pending_pay_out.amount, -START_BALANCE)
        completed_pay_out = await self.order_service.book_pay_out(token=self.terminal_token, new_pay_out=new_pay_out)
        self.assertIsNotNone(completed_pay_out)

        customer = await self.till_service.get_customer(token=self.terminal_token, customer_tag_uid=self.customer_uid)
        self.assertEqual(0, customer.balance)
        await self._assert_account_balance(account_id=self.cashier.cashier_account_id, balance=-START_BALANCE)
        await self._assert_account_balance(account_id=ACCOUNT_CASH_VAULT, balance=START_BALANCE)
        await self._assert_account_balance(account_id=ACCOUNT_CASH_EXIT, balance=START_BALANCE)

    async def test_cash_pay_out_flow_with_amount(self):
        new_pay_out = NewPayOut(customer_tag_uid=self.customer_uid, amount=-2 * START_BALANCE)
        with self.assertRaises(NotEnoughFundsException):
            await self.order_service.check_pay_out(token=self.terminal_token, new_pay_out=new_pay_out)

        new_pay_out = NewPayOut(customer_tag_uid=self.customer_uid, amount=-20)
        pending_pay_out = await self.order_service.check_pay_out(token=self.terminal_token, new_pay_out=new_pay_out)
        self.assertEqual(pending_pay_out.old_balance, START_BALANCE)
        self.assertEqual(pending_pay_out.new_balance, START_BALANCE - 20)
        self.assertEqual(pending_pay_out.amount, -20)

        completed_pay_out = await self.order_service.book_pay_out(token=self.terminal_token, new_pay_out=new_pay_out)
        self.assertIsNotNone(completed_pay_out)

        customer = await self.till_service.get_customer(token=self.terminal_token, customer_tag_uid=self.customer_uid)
        self.assertEqual(START_BALANCE - 20, customer.balance)
        await self._assert_account_balance(account_id=self.cashier.cashier_account_id, balance=-20)
        await self._assert_account_balance(account_id=ACCOUNT_CASH_VAULT, balance=20)
        await self._assert_account_balance(account_id=ACCOUNT_CASH_EXIT, balance=20)

    async def test_only_ticket_till_profiles_can_sell_tickets(self):
        profile = await self.till_service.profile.create_profile(
            token=self.admin_token,
            profile=NewTillProfile(
                name="profile2",
                description="",
                layout_id=self.till_layout.id,
                allow_top_up=False,
                allow_cash_out=False,
                allow_ticket_sale=False,
                allowed_role_names=[ADMIN_ROLE_NAME, FINANZORGA_ROLE_NAME, CASHIER_ROLE_NAME],
            ),
        )
        self.till.active_profile_id = profile.id
        await self.till_service.update_till(token=self.admin_token, till_id=self.till.id, till=self.till)

        with self.assertRaises(TillPermissionException):
            new_ticket_sale = NewTicketSale(
                customer_tag_uid=self.customer_uid, initial_top_up_amount=0, payment_method=PaymentMethod.cash
            )
            await self.order_service.check_ticket_sale(token=self.terminal_token, new_ticket_sale=new_ticket_sale)

    async def test_ticket_flow_no_initial_topup_cash(self):
        new_ticket = NewTicketSale(
            customer_tag_uid=self.unused_tag_uid, initial_top_up_amount=0, payment_method=PaymentMethod.cash
        )
        pending_ticket: PendingTicketSale = await self.order_service.check_ticket_sale(
            token=self.terminal_token, new_ticket_sale=new_ticket
        )
        self.assertEqual(0, pending_ticket.initial_top_up_amount)
        self.assertEqual(1, pending_ticket.item_count)
        self.assertEqual(self.ticket_price, pending_ticket.total_price)
        completed_ticket = await self.order_service.book_ticket_sale(
            token=self.terminal_token, new_ticket_sale=new_ticket
        )
        self.assertIsNotNone(completed_ticket)

        customer = await self.till_service.get_customer(token=self.terminal_token, customer_tag_uid=self.unused_tag_uid)
        self.assertEqual(0, customer.balance)
        await self._assert_account_balance(
            account_id=self.cashier.cashier_account_id, balance=completed_ticket.total_price
        )
        await self._assert_account_balance(account_id=ACCOUNT_CASH_ENTRY, balance=-completed_ticket.total_price)
        await self._assert_account_balance(account_id=ACCOUNT_CASH_VAULT, balance=-completed_ticket.total_price)

    async def test_ticket_flow_with_initial_topup_cash(self):
        new_ticket = NewTicketSale(
            customer_tag_uid=self.unused_tag_uid, initial_top_up_amount=8, payment_method=PaymentMethod.cash
        )
        pending_ticket: PendingTicketSale = await self.order_service.check_ticket_sale(
            token=self.terminal_token, new_ticket_sale=new_ticket
        )
        self.assertEqual(8, pending_ticket.initial_top_up_amount)
        self.assertEqual(2, pending_ticket.item_count)
        self.assertEqual(self.ticket_price + 8, pending_ticket.total_price)
        completed_ticket = await self.order_service.book_ticket_sale(
            token=self.terminal_token, new_ticket_sale=new_ticket
        )
        self.assertIsNotNone(completed_ticket)

        customer = await self.till_service.get_customer(token=self.terminal_token, customer_tag_uid=self.unused_tag_uid)
        self.assertEqual(8, customer.balance)
        await self._assert_account_balance(
            account_id=self.cashier.cashier_account_id, balance=completed_ticket.total_price
        )
        await self._assert_account_balance(account_id=ACCOUNT_CASH_ENTRY, balance=-completed_ticket.total_price)
        await self._assert_account_balance(account_id=ACCOUNT_CASH_VAULT, balance=-completed_ticket.total_price)
        await self._assert_account_balance(account_id=ACCOUNT_SALE_EXIT, balance=self.ticket_price)

    async def test_ticket_flow_with_initial_topup_sumup(self):
        new_ticket = NewTicketSale(
            customer_tag_uid=self.unused_tag_uid, initial_top_up_amount=8, payment_method=PaymentMethod.sumup
        )
        pending_ticket: PendingTicketSale = await self.order_service.check_ticket_sale(
            token=self.terminal_token, new_ticket_sale=new_ticket
        )
        self.assertEqual(8, pending_ticket.initial_top_up_amount)
        self.assertEqual(2, pending_ticket.item_count)
        self.assertEqual(self.ticket_price + 8, pending_ticket.total_price)
        completed_ticket = await self.order_service.book_ticket_sale(
            token=self.terminal_token, new_ticket_sale=new_ticket
        )
        self.assertIsNotNone(completed_ticket)

        customer = await self.till_service.get_customer(token=self.terminal_token, customer_tag_uid=self.unused_tag_uid)
        self.assertEqual(8, customer.balance)
        await self._assert_account_balance(account_id=ACCOUNT_SUMUP, balance=-completed_ticket.total_price)
        await self._assert_account_balance(account_id=ACCOUNT_SALE_EXIT, balance=self.ticket_price)
