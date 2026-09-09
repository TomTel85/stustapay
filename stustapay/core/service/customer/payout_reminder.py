"""Periodic operational reminders for online payouts awaiting export."""

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from email.utils import formataddr

import asyncpg
from dateutil.tz import tzlocal
from sftkit.database import Connection
from sftkit.service import Service, with_db_transaction

from stustapay.core.config import Config
from stustapay.core.schema.user import Privilege
from stustapay.core.service.email_templates import render_payout_reminder_html
from stustapay.core.service.mail import MailService


class PayoutReminderService(Service[Config]):
    """Queues one reminder per eligible recipient for each due event."""

    CHECK_INTERVAL_SECONDS = 60

    def __init__(self, db_pool: asyncpg.Pool, config: Config, mail_service: MailService):
        super().__init__(db_pool, config)
        self.mail_service = mail_service
        self.logger = logging.getLogger("payout_reminder_service")

    @staticmethod
    def next_scheduled_check(*, now: datetime, weekday: int, scheduled_time: time) -> datetime:
        """Return the next strictly future weekly occurrence in the server's local timezone."""
        local_timezone = tzlocal()
        local_now = now.astimezone(local_timezone)
        candidate = datetime.combine(local_now.date(), scheduled_time, tzinfo=local_timezone)
        candidate += timedelta(days=(weekday - candidate.weekday()) % 7)
        if candidate <= local_now:
            candidate += timedelta(days=7)
        return candidate.astimezone(timezone.utc)

    @staticmethod
    def next_check_after(*, scheduled_check: datetime, now: datetime) -> datetime:
        """Advance an overdue schedule beyond now so a restart produces one catch-up reminder."""
        next_check = (scheduled_check.astimezone(tzlocal()) + timedelta(days=7)).astimezone(timezone.utc)
        while next_check <= now:
            next_check = (next_check.astimezone(tzlocal()) + timedelta(days=7)).astimezone(timezone.utc)
        return next_check

    def _message(self, *, event_name: str, count: int, payout_total: Decimal, donation_total: Decimal, currency: str, node_id: int):
        payout_amount = f"{payout_total:.2f} {currency}"
        donation_amount = f"{donation_total:.2f} {currency}"
        payout_url = f"{self.config.administration.base_url.rstrip('/')}/node/{node_id}/payout-runs"
        subject = f"[teamfestlichPay] Offene Auszahlungen: {event_name}"
        message = (
            f"Für {event_name} warten {count} Online-Auszahlung(en) mit insgesamt {payout_amount} "
            f"auf den nächsten Auszahlungslauf. Spenden: {donation_amount}.\n"
            f"Auszahlungen öffnen: {payout_url}\n\n"
            f"For {event_name}, {count} online payout(s) totaling {payout_amount} are waiting "
            f"for the next payout run. Donations: {donation_amount}.\n"
            f"Open payouts: {payout_url}"
        )
        html_message = render_payout_reminder_html(
            event_name=event_name,
            count=count,
            payout_amount=payout_amount,
            donation_amount=donation_amount,
            payout_url=payout_url,
            subject=subject,
        )
        return subject, message, html_message

    @with_db_transaction
    async def process_due_reminders(self, *, conn: Connection, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        due_events = await conn.fetch(
            "select e.id as event_id, n.id as node_id, n.name as event_name, e.currency_identifier, e.payout_sender, "
            "e.payout_reminder_weekday, e.payout_reminder_time, e.payout_reminder_next_check_at "
            "from event e join node n on n.event_id = e.id "
            "where e.payout_reminder_enabled and "
            "(e.payout_reminder_next_check_at is null or e.payout_reminder_next_check_at <= $1) "
            "order by e.id for update of e skip locked",
            now,
        )
        for event in due_events:
            scheduled_check = event["payout_reminder_next_check_at"]
            if scheduled_check is None:
                await conn.execute(
                    "update event set payout_reminder_next_check_at = $2 where id = $1",
                    event["event_id"],
                    self.next_scheduled_check(
                        now=now,
                        weekday=event["payout_reminder_weekday"],
                        scheduled_time=event["payout_reminder_time"],
                    ),
                )
                continue

            next_check = self.next_check_after(scheduled_check=scheduled_check, now=now)
            await conn.execute(
                "update event set payout_reminder_next_check_at = $2 where id = $1", event["event_id"], next_check
            )
            pending = await conn.fetchrow(
                "select coalesce(sum(c.balance), 0) - coalesce(sum(c.donation), 0) as total_payout_amount, "
                "coalesce(sum(c.donation), 0) as total_donation_amount, count(*) as n_payouts "
                "from customers_without_payout_run c where c.node_id = $1",
                event["node_id"],
            )
            if pending["total_payout_amount"] <= 0:
                continue

            recipients = await conn.fetch(
                "select u.id, u.email from payout_reminder_recipient r "
                "join usr u on u.id = r.user_id "
                "join lateral user_privileges_at_node(u.id) up on true "
                "where r.event_id = $1 and u.email is not null and "
                "up.node_id = $2 and ($3 = any(up.privileges_at_node) or $4 = any(up.privileges_at_node))",
                event["event_id"],
                event["node_id"],
                Privilege.payout_management.name,
                Privilege.node_administration.name,
            )
            if not recipients:
                self.logger.warning("No eligible payout reminder recipients for event %s", event["event_id"])
                continue

            subject, message, html_message = self._message(
                event_name=event["event_name"],
                count=pending["n_payouts"],
                payout_total=pending["total_payout_amount"],
                donation_total=pending["total_donation_amount"],
                currency=event["currency_identifier"],
                node_id=event["node_id"],
            )
            for recipient in recipients:
                await self.mail_service.send_mail(
                    conn=conn,
                    node_id=event["node_id"],
                    subject=subject,
                    text_message=message,
                    html_message=html_message,
                    from_addr=(
                        formataddr((f"{event['event_name']} Auszahlung", event["payout_sender"]))
                        if event["payout_sender"]
                        else None
                    ),
                    to_addr=recipient["email"],
                )

    async def run_payout_reminder_service(self) -> None:
        self.logger.info("Starting periodic job to check pending online payouts")
        while True:
            try:
                await self.process_due_reminders()
            except Exception:
                self.logger.exception("Failed to process payout reminders")
            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
