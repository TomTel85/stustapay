"""Durable offline preparation and idempotent reconciliation of tag sales."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from asyncpg import IntegrityConstraintViolationError
from sftkit.database import Connection
from sftkit.service import with_db_transaction

from stustapay.core.schema.offline import (
    OfflineBooking,
    OfflineBookingResult,
    OfflineBookingStatus,
    OfflineButton,
    OfflineCustomer,
    OfflineDeviceStatus,
    OfflineImport,
    OfflineImportResult,
    OfflineLimits,
    OfflineReportEntry,
    OfflineSnapshot,
)
from stustapay.core.schema.order import CompletedSale, NewSale, PaymentMethod, PendingLineItem, PendingSale
from stustapay.core.schema.product import ProductType
from stustapay.core.schema.terminal import CurrentTerminal
from stustapay.core.schema.till import Till
from stustapay.core.schema.tree import Node
from stustapay.core.schema.user import CurrentUser, Privilege
from stustapay.core.service.common.decorators import requires_node, requires_terminal, requires_user
from stustapay.core.service.common.error import InvalidArgument, ServiceException
from stustapay.core.service.order.pending_order import make_sale_bookings
from stustapay.core.service.tree.common import fetch_node, fetch_restricted_event_settings_for_node


def cents(value: float) -> int:
    return int((Decimal(str(value)) * 100).to_integral_value())


def offline_price_cents(value: float) -> int:
    """Accept nonnegative money with exact cent precision, without silently rounding."""
    amount = Decimal(str(value)) * 100
    if not amount.is_finite() or amount < 0 or amount > 2**63 - 1 or amount != amount.to_integral_value():
        raise InvalidArgument("Offline price must be nonnegative and have at most two decimal places")
    return int(amount)


def json_object(value):
    """Support the database's JSON codec and older encoded JSON strings."""
    return json.loads(value) if isinstance(value, str) else value


def offline_positions(snapshot: OfflineSnapshot, sale: NewSale) -> tuple[list[PendingLineItem], int, int]:
    """Validate a historical sale and count gross debits and returns separately."""
    if sale.payment_method != PaymentMethod.tag or sale.customer_tag_uid is None or sale.used_vouchers != 0:
        raise InvalidArgument("Offline sales require tag payment and explicitly zero vouchers")
    customer = next((c for c in snapshot.customers if c.customer_tag_uid == sale.customer_tag_uid), None)
    if customer is None:
        raise InvalidArgument("Unknown offline customer")
    buttons = {b.id: b for b in snapshot.buttons}
    lines: dict[tuple[int, int], PendingLineItem] = {}
    positive = negative = 0
    if not sale.buttons:
        raise InvalidArgument("Empty offline sale")
    for button in sale.buttons:
        selected = buttons.get(button.till_button_id)
        if selected is None or not selected.products:
            raise InvalidArgument("Unknown or empty prepared button")
        free_price = len(selected.products) == 1 and not selected.products[0].fixed_price
        if free_price:
            if button.price is None or button.quantity is not None or selected.products[0].is_returnable:
                raise InvalidArgument("Offline free prices require one non-returnable product and an amount")
            quantity = 1
            entered_cents = offline_price_cents(button.price)
        else:
            if button.price is not None or button.quantity is None or button.quantity == 0:
                raise InvalidArgument("Prepared fixed-price buttons require a quantity and no price override")
            quantity = button.quantity
            entered_cents = None
        for product in selected.products:
            if product.type != ProductType.user_defined or (not free_price and not product.fixed_price):
                raise InvalidArgument("Unsupported offline product")
            if quantity < 0 and not product.is_returnable:
                raise InvalidArgument("Product cannot be returned")
            if customer.restriction in product.restrictions:
                raise InvalidArgument("Age restricted product")
            if entered_cents is not None:
                unit_cents = entered_cents
            elif product.price is not None:
                unit_cents = offline_price_cents(product.price)
            else:
                raise InvalidArgument("Missing prepared product price")
            amount = unit_cents * quantity
            positive += max(amount, 0)
            negative += max(-amount, 0)
            key = (product.id, unit_cents)
            if key not in lines:
                lines[key] = PendingLineItem(
                    product=product,
                    quantity=quantity,
                    product_price=unit_cents / 100,
                    tax_rate_id=product.tax_rate_id,
                    tax_name=product.tax_name,
                    tax_rate=product.tax_rate,
                )
            else:
                lines[key].quantity += quantity
    positions = [line for line in lines.values() if line.quantity != 0]
    if not positions:
        raise InvalidArgument("Empty resulting offline sale")
    return positions, positive, negative


def check_offline_budget(
    snapshot: OfflineSnapshot, sale: NewSale, positive: int, negative: int, history: list[tuple[int, int, int]]
) -> None:
    """History contains (tag UID, gross debit, gross return); credits never replenish budgets."""
    rules = snapshot.rules
    customer = next(c for c in snapshot.customers if c.customer_tag_uid == sale.customer_tag_uid)
    own = [(p, n) for uid, p, n in history if uid == sale.customer_tag_uid]
    checks = (
        (positive, rules.sale_per_transaction_cents),
        (negative, rules.return_per_transaction_cents),
        (positive + sum(p for p, _ in own), rules.sale_per_customer_cents),
        (negative + sum(n for _, n in own), rules.return_per_customer_cents),
        (positive + sum(p for _, p, _ in history), rules.sale_per_till_cents),
        (negative + sum(n for _, _, n in history), rules.return_per_till_cents),
    )
    if any(amount > limit for amount, limit in checks):
        raise InvalidArgument("Offline budget exceeded")
    available = max(0, customer.balance_cents) - sum(max(0, p - n) for p, n in own)
    if max(0, positive - negative) > available:
        raise InvalidArgument("Offline estimated balance exceeded")


class OfflineOrderMixin:
    @with_db_transaction(read_only=False)
    @requires_terminal(user_privileges=[Privilege.can_book_orders])
    async def prepare_offline(
        self,
        *,
        conn: Connection,
        node: Node,
        current_till: Till,
        current_terminal: CurrentTerminal,
        current_user: CurrentUser,
    ) -> OfflineSnapshot:
        settings = await fetch_restricted_event_settings_for_node(conn=conn, node_id=node.id)
        if not settings.offline_enabled:
            raise InvalidArgument("Offline operation is disabled")
        profile = await conn.fetchrow("select * from till_profile where id = $1", current_till.active_profile_id)
        if profile is None or not profile["enable_ssp_payment"]:
            raise InvalidArgument("Tag payments are disabled")
        if await conn.fetchval(
            "select exists(select 1 from terminal_offline_import i join terminal_offline_snapshot s on s.id=i.snapshot_id "
            "where s.terminal_id=$1 and i.resolved_at is null and i.result->>'status'='clarification_required')",
            current_terminal.id,
        ):
            raise InvalidArgument("Offline clarification must be resolved before preparing again")
        if await conn.fetchval(
            "select exists(select 1 from terminal_offline_rejection where terminal_id=$1 and resolved_at is null)",
            current_terminal.id,
        ):
            raise InvalidArgument("Offline clarification must be resolved before preparing again")
        # One SQL statement captures customer balances and full button products at one MVCC instant.
        state = await conn.fetchrow(
            "select (select coalesce(jsonb_agg(jsonb_build_object('customer_account_id',a.id,"
            "'customer_tag_uid',ut.uid,'balance_cents',round(a.balance*100)::bigint,'restriction',ut.restriction)), '[]') "
            "from account a join user_tag ut on ut.id=a.user_tag_id join node n on n.id=a.node_id "
            "where a.type='private' and ut.uid is not null and (n.id=$1 or $1=any(n.parent_ids))) as customers, "
            "(select coalesce(jsonb_agg(b), '[]') from (select tb.id,tb.name, "
            "jsonb_agg(to_jsonb(p)) as products from till_button tb "
            "join till_layout_to_button lb on lb.button_id=tb.id "
            "join till_button_product bp on bp.button_id=tb.id "
            "join product_with_tax_and_restrictions p on p.id=bp.product_id "
            "where lb.layout_id=$2 group by tb.id,tb.name) b) as buttons",
            node.event_node_id,
            profile["layout_id"],
        )
        assert state is not None and node.event_node_id is not None
        now = datetime.now(timezone.utc)
        rules = OfflineLimits(**{k: getattr(settings, "offline_" + k) for k in OfflineLimits.model_fields})
        scope_ids = node.ids_to_event_node
        assert scope_ids is not None
        buttons = [OfflineButton.model_validate(b) for b in json_object(state["buttons"])]
        buttons = [
            b
            for b in buttons
            if b.products
            and all(p.type == ProductType.user_defined and p.node_id in scope_ids for p in b.products)
            and (
                all(p.fixed_price and p.price is not None and p.price >= 0 for p in b.products)
                or (len(b.products) == 1 and not b.products[0].fixed_price and not b.products[0].is_returnable)
            )
        ]
        snapshot = OfflineSnapshot(
            id=uuid4(),
            server_time=now,
            valid_until=now + timedelta(seconds=rules.validity_seconds),
            terminal_id=current_terminal.id,
            till_id=current_till.id,
            event_node_id=node.event_node_id,
            user_id=current_user.id,
            rules=rules,
            customers=[OfflineCustomer.model_validate(c) for c in json_object(state["customers"])],
            buttons=buttons,
        )
        session_uuid = await conn.fetchval("select session_uuid from terminal where id=$1", current_terminal.id)
        await conn.execute(
            "insert into terminal_offline_snapshot "
            "(id,terminal_id,session_uuid,event_node_id,till_id,user_id,prepared_at,valid_until,last_contact_at,"
            "snapshot,till_config,cash_register_id) values($1,$2,$3,$4,$5,$6,$7,$8,$7,$9,$10,$11)",
            snapshot.id,
            current_terminal.id,
            session_uuid,
            snapshot.event_node_id,
            current_till.id,
            current_user.id,
            now,
            snapshot.valid_until,
            snapshot.model_dump(mode="json"),
            current_till.model_dump(mode="json"),
            current_user.cash_register_id,
        )
        return snapshot

    @with_db_transaction(read_only=False)
    @requires_terminal(requires_till=False)
    async def import_offline(
        self, *, conn: Connection, current_terminal: CurrentTerminal, payload: OfflineImport
    ) -> OfflineImportResult:
        results = []
        for booking in sorted(payload.bookings, key=lambda b: (str(b.snapshot_id), b.sequence)):
            # Savepoints let one invalid booking coexist with valid later records.
            try:
                async with conn.transaction():
                    result = await self._import_offline_booking(conn=conn, terminal=current_terminal, booking=booking)
            except (ServiceException, ValueError, IntegrityConstraintViolationError) as exc:
                result = OfflineBookingResult(
                    uuid=booking.sale.uuid, status=OfflineBookingStatus.clarification_required, message=str(exc)
                )
                await self._save_offline_result(conn=conn, terminal=current_terminal, booking=booking, result=result)
            results.append(result)
        return OfflineImportResult(results=results)

    async def _save_offline_result(
        self, *, conn: Connection, terminal: CurrentTerminal, booking: OfflineBooking, result: OfflineBookingResult
    ) -> None:
        # Never let foreign snapshot identifiers reserve another terminal's booking UUID.
        own = await conn.fetchval(
            "select exists(select 1 from terminal_offline_snapshot where id=$1 and terminal_id=$2)",
            booking.snapshot_id,
            terminal.id,
        )
        if not own:
            await conn.execute(
                "insert into terminal_offline_rejection(terminal_id,node_id,till_id,user_id,request,result) "
                "values($1,$2,$3,$4,$5,$6)",
                terminal.id,
                terminal.node_id,
                terminal.till.id if terminal.till is not None else 0,
                terminal.active_user_id or 0,
                booking.model_dump(mode="json"),
                result.model_dump(mode="json"),
            )
            return
        existing = await conn.fetchrow("select request from terminal_offline_import where uuid=$1", booking.sale.uuid)
        if existing and json_object(existing["request"]) != booking.model_dump(mode="json"):
            await conn.execute(
                "insert into terminal_offline_rejection(terminal_id,node_id,till_id,user_id,request,result) "
                "values($1,$2,$3,$4,$5,$6)",
                terminal.id,
                terminal.node_id,
                terminal.till.id if terminal.till is not None else 0,
                terminal.active_user_id or 0,
                booking.model_dump(mode="json"),
                result.model_dump(mode="json"),
            )
            return
        if own:
            await conn.execute(
                "insert into terminal_offline_import(uuid,snapshot_id,sequence,request,result) values($1,$2,$3,$4,$5) "
                "on conflict do nothing",
                booking.sale.uuid,
                booking.snapshot_id,
                booking.sequence,
                booking.model_dump(mode="json"),
                result.model_dump(mode="json"),
            )

    async def _import_offline_booking(
        self, *, conn: Connection, terminal: CurrentTerminal, booking: OfflineBooking
    ) -> OfflineBookingResult:
        row = await conn.fetchrow(
            "select * from terminal_offline_snapshot where id=$1 and terminal_id=$2 for update",
            booking.snapshot_id,
            terminal.id,
        )
        if row is None:
            raise InvalidArgument("Snapshot does not belong to this terminal")
        await conn.execute(
            "update terminal_offline_snapshot set last_contact_at=now() where id=$1", booking.snapshot_id
        )
        await conn.execute("select pg_advisory_xact_lock(hashtextextended($1,0))", str(booking.sale.uuid))
        existing = await conn.fetchrow("select * from terminal_offline_import where uuid=$1", booking.sale.uuid)
        if existing:
            if json_object(existing["request"]) != booking.model_dump(mode="json"):
                raise InvalidArgument("Booking UUID reused with different content")
            result = OfflineBookingResult.model_validate(json_object(existing["result"]))
            if existing["resolved_at"] is not None:
                result.status = OfflineBookingStatus.dismissed
            if result.status == OfflineBookingStatus.booked:
                result.status = OfflineBookingStatus.already_booked
            return result
        # Recover an online booking whose acknowledgement was lost, using its original UUID.
        cached = await conn.fetchrow("select * from terminal_sale_journal where uuid=$1", booking.sale.uuid)
        if cached:
            if cached["terminal_id"] != terminal.id or json_object(cached["request"]) != booking.sale.model_dump(
                mode="json"
            ):
                raise InvalidArgument("Booking UUID reused with different sale")
            completed = CompletedSale.model_validate(json_object(cached["result"]))
            result = OfflineBookingResult(
                uuid=booking.sale.uuid, status=OfflineBookingStatus.already_booked, sale=completed
            )
            await self._save_offline_result(conn=conn, terminal=terminal, booking=booking, result=result)
            return result
        last_sequence = await conn.fetchval(
            "select max(sequence) from terminal_offline_import where snapshot_id=$1", booking.snapshot_id
        )
        if last_sequence is not None and booking.sequence <= last_sequence:
            raise InvalidArgument("Offline booking sequence is not increasing")
        session_uuid = await conn.fetchval("select session_uuid from terminal where id=$1", terminal.id)
        if session_uuid != row["session_uuid"]:
            raise InvalidArgument("Terminal registration changed")
        snapshot = OfflineSnapshot.model_validate(json_object(row["snapshot"]))
        if not snapshot.server_time <= booking.recorded_at <= snapshot.valid_until:
            raise InvalidArgument("Sale was recorded outside preparation validity")
        if booking.recorded_at > datetime.now(timezone.utc) + timedelta(seconds=30):
            raise InvalidArgument("Sale timestamp is in the future")
        lines, positive, negative = offline_positions(snapshot, booking.sale)
        history = []
        for record in await conn.fetch(
            "select request from terminal_offline_import where snapshot_id=$1 "
            "and result->>'status' in ('booked','already_booked')",
            snapshot.id,
        ):
            previous = OfflineBooking.model_validate(json_object(record["request"]))
            _, p, n = offline_positions(snapshot, previous.sale)
            assert previous.sale.customer_tag_uid is not None
            history.append((previous.sale.customer_tag_uid, p, n))
        check_offline_budget(snapshot, booking.sale, positive, negative, history)
        if await conn.fetchval("select exists(select 1 from ordr where uuid=$1)", booking.sale.uuid):
            raise InvalidArgument("Legacy order exists without a verifiable original request")
        customer = next(c for c in snapshot.customers if c.customer_tag_uid == booking.sale.customer_tag_uid)
        await conn.fetchrow("select id from account where id=$1 for update", customer.customer_account_id)
        balance = await conn.fetchval("select balance from account where id=$1", customer.customer_account_id)
        if balance is None:
            raise InvalidArgument("Customer account no longer exists")
        node = await fetch_node(conn=conn, node_id=json_object(row["till_config"])["node_id"])
        if node is None or node.read_only or node.event_node_id != snapshot.event_node_id:
            raise InvalidArgument("Original event is unavailable or read only")
        total_cents = positive - negative
        pending = PendingSale(
            uuid=booking.sale.uuid,
            buttons=booking.sale.buttons,
            line_items=lines,
            old_balance=float(balance),
            new_balance=float(balance) - total_cents / 100,
            old_voucher_balance=0,
            new_voucher_balance=0,
            customer_account_id=customer.customer_account_id,
            payment_method=PaymentMethod.tag,
        )
        completed = await make_sale_bookings(
            conn=conn,
            node=node,
            current_till=Till.model_validate(json_object(row["till_config"])),
            current_user_id=snapshot.user_id,
            sale=pending,
            cash_register_id=row["cash_register_id"],
            buttons=booking.sale.buttons,
            z_nr=json_object(row["till_config"])["z_nr"],
        )
        settings = await fetch_restricted_event_settings_for_node(conn=conn, node_id=node.id)
        completed.bon_url = settings.customer_portal_url + "/bon/" + str(completed.uuid)
        await conn.execute(
            "insert into terminal_sale_journal(uuid,terminal_id,request,result) values($1,$2,$3,$4)",
            completed.uuid,
            terminal.id,
            booking.sale.model_dump(mode="json"),
            completed.model_dump(mode="json"),
        )
        result = OfflineBookingResult(uuid=completed.uuid, status=OfflineBookingStatus.booked, sale=completed)
        await self._save_offline_result(conn=conn, terminal=terminal, booking=booking, result=result)
        return result

    @with_db_transaction(read_only=True)
    @requires_terminal(requires_till=False)
    async def offline_booking_status(
        self, *, conn: Connection, current_terminal: CurrentTerminal, order_uuid: UUID
    ) -> OfflineBookingResult:
        cached = await conn.fetchrow(
            "select result from terminal_sale_journal where uuid=$1 and terminal_id=$2", order_uuid, current_terminal.id
        )
        if cached:
            return OfflineBookingResult(
                uuid=order_uuid,
                status=OfflineBookingStatus.already_booked,
                sale=CompletedSale.model_validate(json_object(cached["result"])),
            )
        dismissed = await conn.fetchval(
            "select exists(select 1 from terminal_offline_import i join terminal_offline_snapshot s on s.id=i.snapshot_id "
            "where i.uuid=$1 and s.terminal_id=$2 and i.resolved_at is not null)",
            order_uuid,
            current_terminal.id,
        )
        if dismissed:
            return OfflineBookingResult(uuid=order_uuid, status=OfflineBookingStatus.dismissed)
        result = await conn.fetchval(
            "select i.result from terminal_offline_import i join terminal_offline_snapshot s "
            "on s.id=i.snapshot_id where i.uuid=$1 and s.terminal_id=$2",
            order_uuid,
            current_terminal.id,
        )
        if result:
            return OfflineBookingResult.model_validate(json_object(result))
        rejection = await conn.fetchrow(
            "select result,resolved_at from terminal_offline_rejection where terminal_id=$1 "
            "and request->'sale'->>'uuid'=$2 order by received_at desc limit 1",
            current_terminal.id,
            str(order_uuid),
        )
        if rejection:
            result = OfflineBookingResult.model_validate(json_object(rejection["result"]))
            if rejection["resolved_at"] is not None:
                result.status = OfflineBookingStatus.dismissed
            return result
        return OfflineBookingResult(uuid=order_uuid, status=OfflineBookingStatus.not_found)

    @with_db_transaction(read_only=True)
    @requires_node()
    @requires_user([Privilege.node_administration])
    async def offline_report(self, *, conn: Connection, node: Node) -> list[OfflineReportEntry]:
        records = await conn.fetch(
            "select i.*,s.terminal_id,s.till_id,s.user_id from terminal_offline_import i "
            "join terminal_offline_snapshot s on s.id=i.snapshot_id join node n on n.id=s.event_node_id "
            "where n.id=$1 or $1=any(n.parent_ids) order by i.received_at desc limit 1000",
            node.id,
        )
        rejections = await conn.fetch(
            "select (r.request->'sale'->>'uuid')::uuid as uuid,(r.request->>'snapshot_id')::uuid as snapshot_id,"
            "r.request,r.result,r.received_at,r.terminal_id,r.till_id,r.user_id,r.resolved_at "
            "from terminal_offline_rejection r join node n on n.id=r.node_id "
            "where n.id=$1 or $1=any(n.parent_ids) order by r.received_at desc limit 1000",
            node.id,
        )
        records = sorted([*records, *rejections], key=lambda row: row["received_at"], reverse=True)[:1000]
        report = []
        for row in records:
            result = OfflineBookingResult.model_validate(json_object(row["result"]))
            request = OfflineBooking.model_validate(json_object(row["request"]))
            report.append(
                OfflineReportEntry(
                    uuid=row["uuid"],
                    snapshot_id=row["snapshot_id"],
                    terminal_id=row["terminal_id"],
                    till_id=row["till_id"],
                    user_id=row["user_id"],
                    recorded_at=request.recorded_at,
                    received_at=row["received_at"],
                    status=OfflineBookingStatus.dismissed if row["resolved_at"] is not None else result.status,
                    message=result.message,
                    customer_account_id=result.sale.customer_account_id if result.sale else None,
                    new_balance=result.sale.new_balance if result.sale else None,
                    order_id=result.sale.id if result.sale else None,
                )
            )
        return report

    @with_db_transaction(read_only=True)
    @requires_node()
    @requires_user([Privilege.node_administration])
    async def offline_devices(self, *, conn: Connection, node: Node) -> list[OfflineDeviceStatus]:
        return await conn.fetch_many(
            OfflineDeviceStatus,
            "select distinct on (s.terminal_id) s.terminal_id,s.till_id,s.user_id,s.id as snapshot_id,"
            "s.last_contact_at,s.valid_until from terminal_offline_snapshot s join node n on n.id=s.event_node_id "
            "where n.id=$1 or $1=any(n.parent_ids) order by s.terminal_id,s.prepared_at desc",
            node.id,
        )

    @with_db_transaction(read_only=False)
    @requires_node()
    @requires_user([Privilege.node_administration])
    async def dismiss_offline(
        self, *, conn: Connection, node: Node, current_user: CurrentUser, order_uuid: UUID
    ) -> None:
        """A reviewer acknowledges an unbooked sale after handling it manually; never deletes the audit trail."""
        row = await conn.fetchrow(
            "select i.* from terminal_offline_import i join terminal_offline_snapshot s on s.id=i.snapshot_id "
            "join node n on n.id=s.event_node_id where i.uuid=$1 and (n.id=$2 or $2=any(n.parent_ids)) for update of i",
            order_uuid,
            node.id,
        )
        rejection_ids = await conn.fetch(
            "select r.id from terminal_offline_rejection r join node n on n.id=r.node_id "
            "where r.request->'sale'->>'uuid'=$1 "
            "and (n.id=$2 or $2=any(n.parent_ids)) and r.resolved_at is null for update of r",
            str(order_uuid),
            node.id,
        )
        eligible = row is not None and json_object(row["result"])["status"] == "clarification_required"
        if not eligible and not rejection_ids:
            raise InvalidArgument("Only an unbooked clarification can be dismissed")
        if eligible:
            await conn.execute(
                "update terminal_offline_import set resolved_at=now(),resolved_by=$2 where uuid=$1",
                order_uuid,
                current_user.id,
            )
        if rejection_ids:
            await conn.execute(
                "update terminal_offline_rejection set resolved_at=now(),resolved_by=$2 where id=any($1)",
                [r["id"] for r in rejection_ids],
                current_user.id,
            )
