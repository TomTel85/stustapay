from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from sftkit.database import Connection

from stustapay.core.config import Config
from stustapay.core.schema.tree import Node
from stustapay.core.schema.user import User
from stustapay.core.service.customer.payout_reminder import PayoutReminderService


def _service(config: Config) -> PayoutReminderService:
    return PayoutReminderService(db_pool=None, config=config, mail_service=Mock())  # type: ignore[arg-type]


def test_next_scheduled_check_uses_next_week_when_today_has_passed(config: Config):
    service = _service(config)

    next_check = service.next_scheduled_check(
        now=datetime(2026, 9, 7, 10, tzinfo=timezone.utc), weekday=0, scheduled_time=time(hour=9)
    )

    assert next_check > datetime(2026, 9, 7, 10, tzinfo=timezone.utc)
    assert next_check.astimezone().weekday() == 0


def test_next_check_after_skips_missed_weeks(config: Config):
    service = _service(config)
    now = datetime(2026, 9, 28, 10, tzinfo=timezone.utc)

    next_check = service.next_check_after(
        scheduled_check=datetime(2026, 9, 7, 9, tzinfo=timezone.utc), now=now
    )

    assert next_check > now
    assert next_check.astimezone().weekday() == 0


def test_payout_reminder_message_is_bilingual_and_links_to_the_event(config: Config):
    service = _service(config)

    subject, message, html_message = service._message(
        event_name="Test Festival",
        count=2,
        payout_total=Decimal("12.50"),
        donation_total=Decimal("1.25"),
        currency="EUR",
        node_id=42,
    )

    assert "Offene Auszahlungen" in subject
    assert "12.50 EUR" in message
    assert "1.25 EUR" in message
    assert "http://localhost:8081/node/42/payout-runs" in message
    assert "Auszahlungen öffnen" in html_message
    assert "http://localhost:8081/node/42/payout-runs" in html_message


async def test_due_reminder_queues_one_email_and_advances_the_schedule(
    config: Config,
    db_connection: Connection,
    event_node: Node,
    event_admin_user: tuple[User, str],
    create_random_user_tag,
):
    admin, _ = event_admin_user
    await db_connection.execute("update usr set email = 'payout-admin@example.test' where id = $1", admin.id)
    customer_tag = await create_random_user_tag()
    customer_account_id = await db_connection.fetchval(
        "insert into account (node_id, user_tag_id, balance, type) values ($1, $2, 12.5, 'private') returning id",
        event_node.id,
        customer_tag.id,
    )
    await db_connection.execute(
        "update customer_info set iban = 'DE89370400440532013000', account_name = 'Payout Customer', "
        "email = 'customer@example.test', has_entered_info = true, payout_export = true where customer_account_id = $1",
        customer_account_id,
    )
    now = datetime.now(timezone.utc)
    await db_connection.execute(
        "update event set payout_reminder_enabled = true, payout_sender = 'payout@teamfestlichpay.de', "
        "payout_reminder_next_check_at = $2 "
        "where id = $1",
        event_node.event.id,
        now - timedelta(minutes=1),
    )
    await db_connection.execute(
        "insert into payout_reminder_recipient (event_id, user_id) values ($1, $2)", event_node.event.id, admin.id
    )
    mail_service = AsyncMock()
    service = PayoutReminderService(db_pool=None, config=config, mail_service=mail_service)  # type: ignore[arg-type]

    await service.process_due_reminders(conn=db_connection, now=now)
    await service.process_due_reminders(conn=db_connection, now=now)

    mail_service.send_mail.assert_awaited_once()
    assert mail_service.send_mail.await_args.kwargs["to_addr"] == "payout-admin@example.test"
    assert mail_service.send_mail.await_args.kwargs["from_addr"] == f"{event_node.name} Auszahlung <payout@teamfestlichpay.de>"
    assert "12.50 EUR" in mail_service.send_mail.await_args.kwargs["text_message"]
    assert await db_connection.fetchval("select payout_reminder_next_check_at > $1 from event where id = $2", now, event_node.event.id)
