# pylint: disable=protected-access
import asyncio
from datetime import datetime
from email.message import Message
from unittest.mock import AsyncMock

import pytest
from sftkit.error import NotFound

from stustapay.core.schema.mail import Mail
from stustapay.core.schema.tree import ROOT_NODE_ID
from stustapay.core.service.mail import MailService


async def test_fetch_mail_claims_rows(mail_service: MailService, db_connection):
    await db_connection.execute("delete from mails")

    mail_id = await db_connection.fetchval(
        """
        insert into mails (node_id, subject, text_message, to_addr, from_addr, scheduled_send_date, retry_max)
        values ($1, $2, $3, $4, $5, now(), $6)
        returning id
        """,
        ROOT_NODE_ID,
        "Claim test",
        "hello",
        "recipient@example.test",
        "noreply@example.test",
        5,
    )

    first_claim = await mail_service._fetch_mail()
    second_claim = await mail_service._fetch_mail()

    assert len(first_claim) == 1
    assert first_claim[0].id == mail_id
    assert second_claim == []


@pytest.mark.asyncio
async def test_send_mail_sets_delivery_headers(mail_service: MailService, monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    async def fake_send(message, **kwargs):
        captured["message"] = message
        captured["kwargs"] = kwargs

    monkeypatch.setattr("stustapay.core.service.mail.aiosmtplib.send", fake_send)
    monkeypatch.setattr(
        mail_service,
        "_fetch_global_mail_config",
        AsyncMock(return_value=(True, "noreply@teamfestlichpay.de", "smtp.example.test", 587, "user", "secret")),
    )

    mail = Mail(
        id=123,
        node_id=ROOT_NODE_ID,
        subject="Payout registered",
        text_message="hello world",
        html_message="<p>hello world</p>",
        to_addr="recipient@example.test",
        from_addr="payout@teamfestlichpay.de",
        send_date=None,
        scheduled_send_date=datetime.now(),
        retry_count=0,
        retry_max=5,
        retry_next_attempt=None,
        failure_reason=None,
        attachments=[],
    )

    await mail_service._send_mail(mail=mail)

    message = captured["message"]
    assert isinstance(message, Message)
    assert message["From"] == "teamfestlichPay <payout@teamfestlichpay.de>"
    assert message["Reply-To"] == "teamfestlichPay <payout@teamfestlichpay.de>"
    assert message["Message-ID"].endswith("@teamfestlichpay.de>")


async def test_resolve_mail_settings_uses_event_smtp_config(
    mail_service: MailService, db_connection, event_node, monkeypatch: pytest.MonkeyPatch
):
    event_id = await db_connection.fetchval("select event_id from node where id = $1", event_node.id)
    await db_connection.execute(
        """
        update event
        set email_use_global_settings = false,
            email_default_sender = 'event@example.test',
            email_smtp_host = 'smtp.event.test',
            email_smtp_port = 2525,
            email_smtp_username = 'event-user',
            email_smtp_password = 'event-secret'
        where id = $1
        """,
        event_id,
    )
    fetch_global = AsyncMock()
    monkeypatch.setattr(mail_service, "_fetch_global_mail_config", fetch_global)

    settings = await mail_service._resolve_mail_settings(conn=db_connection, node_id=event_node.id)

    assert settings == (True, "event@example.test", "smtp.event.test", 2525, "event-user", "event-secret")
    fetch_global.assert_not_awaited()


async def test_resolve_mail_settings_rejects_unknown_node(mail_service: MailService, db_connection):
    with pytest.raises(NotFound):
        await mail_service._resolve_mail_settings(conn=db_connection, node_id=-1)


async def test_fetch_mail_claims_only_next_due_message(mail_service: MailService, db_connection):
    await db_connection.execute("delete from mails")
    mail_ids = []
    for i in range(3):
        mail_ids.append(
            await db_connection.fetchval(
                "insert into mails (node_id, subject, text_message, to_addr, from_addr, scheduled_send_date) "
                "values ($1, $2, 'hello', 'recipient@example.test', 'sender@example.test', now()) returning id",
                ROOT_NODE_ID,
                f"Bounded claim {i}",
            )
        )

    first_claim = await mail_service._fetch_mail()
    assert [mail.id for mail in first_claim] == mail_ids[:1]
    unclaimed_ids = await db_connection.fetch("select id from mails where retry_next_attempt is null order by id")
    assert [row["id"] for row in unclaimed_ids] == mail_ids[1:]
    second_claim = await mail_service._fetch_mail()
    assert [mail.id for mail in second_claim] == mail_ids[1:2]


async def test_mail_runner_paces_delivery_and_claims_just_in_time(
    mail_service: MailService, monkeypatch: pytest.MonkeyPatch
):
    claimed_mail = object()
    sleeps = []
    fetch = AsyncMock(side_effect=[[claimed_mail], [], asyncio.CancelledError()])
    send = AsyncMock()

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(mail_service, "_fetch_mail", fetch)
    monkeypatch.setattr(mail_service, "_send_mail", send)
    monkeypatch.setattr("stustapay.core.service.mail.asyncio.sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await mail_service.run_mail_service()

    send.assert_awaited_once_with(mail=claimed_mail)
    assert sleeps == [1.0, 0.05, 1.0]


@pytest.mark.parametrize("smtp_result", ["success", "error", "timeout", "cancelled"])
async def test_mail_delivery_records_result_without_holding_database_connection(
    mail_service: MailService, db_connection, monkeypatch: pytest.MonkeyPatch, smtp_result: str
):
    await db_connection.execute("delete from mails")
    mail_id = await db_connection.fetchval(
        "insert into mails (node_id, subject, text_message, to_addr, from_addr, scheduled_send_date) "
        "values ($1, 'Delivery', 'hello', 'recipient@example.test', 'sender@example.test', now()) returning id",
        ROOT_NODE_ID,
    )
    mail = (await mail_service._fetch_mail())[0]
    lease_until = await db_connection.fetchval("select retry_next_attempt from mails where id = $1", mail_id)
    monkeypatch.setattr(
        mail_service,
        "_fetch_global_mail_config",
        AsyncMock(return_value=(True, "sender@example.test", "smtp.example.test", 587, "user", "secret")),
    )

    async def send(_message, **_kwargs):
        # Only the fixture connection should be checked out during external I/O.
        assert mail_service.db_pool.get_size() - mail_service.db_pool.get_idle_size() == 1
        if smtp_result == "error":
            raise RuntimeError("SMTP unavailable")
        if smtp_result == "timeout":
            await asyncio.sleep(1)
        if smtp_result == "cancelled":
            raise asyncio.CancelledError()

    monkeypatch.setattr("stustapay.core.service.mail.aiosmtplib.send", send)
    if smtp_result == "timeout":
        monkeypatch.setattr(mail_service, "SMTP_TIMEOUT_SECONDS", 0.01)
    if smtp_result == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await mail_service._send_mail(mail=mail)
    else:
        await mail_service._send_mail(mail=mail)
    row = await db_connection.fetchrow("select * from mails where id = $1", mail_id)
    if smtp_result in {"error", "timeout"}:
        assert row["send_date"] is None
        assert row["retry_count"] == 1
        assert row["failure_reason"] == ("SMTP unavailable" if smtp_result == "error" else "TimeoutError")
        assert row["retry_next_attempt"] < lease_until
    elif smtp_result == "cancelled":
        assert row["send_date"] is None
        assert row["retry_count"] == 0
        assert row["retry_next_attempt"] == lease_until
    else:
        assert row["send_date"] is not None
        assert row["retry_count"] == 0
