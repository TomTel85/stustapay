"""Service to handle mail sending."""

# pylint: disable=missing-kwoa
import asyncio
import logging
from datetime import datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

import aiosmtplib
import asyncpg
from sftkit.database import Connection
from sftkit.service import Service, with_db_transaction

from stustapay.core.config import Config
from stustapay.core.schema.mail import Mail
from stustapay.core.service.tree.common import fetch_restricted_event_settings_for_node


class MailService(Service[Config]):
    MAIL_SEND_CHECK_INTERVAL = timedelta(seconds=1)
    MAIL_SEND_INTERVAL = timedelta(seconds=0.05)
    MAX_RETRY_COUNT = 5
    # Doubling backoff pattern for retries: 1sec, 2sec, 4sec, 8sec, 16sec
    BASE_RETRY_DELAY = timedelta(seconds=1)
    BACKOFF_FACTOR = 2  # Double the delay on each retry

    def __init__(self, db_pool: asyncpg.Pool, config: Config):
        super().__init__(db_pool, config)
        self.logger = logging.getLogger("mail_service")

    @with_db_transaction
    async def send_mail(
        self,
        *,
        conn: Connection,
        node_id: int,
        subject: str,
        message: str,
        html_message: bool = False,
        to_addr: str,
        from_addr: str | None = None,
        scheduled_send_date: datetime | None = None,
        attachments: dict[str, bytes] | None = None,
        retry_max: int | None = None,
    ):
        res_config = await fetch_restricted_event_settings_for_node(conn, node_id)
        if not res_config.email_enabled:
            self.logger.warning(
                f"Mail to {to_addr} was not scheduled for sending because event with node id {node_id} has mail sending deactivated"
            )
            return
        mail_id = await conn.fetchval(
            """
            INSERT INTO mails (node_id, subject, message, html_message, to_addr, from_addr, scheduled_send_date, retry_max)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            node_id,
            subject,
            message,
            html_message,
            to_addr,
            from_addr if from_addr is not None else res_config.email_default_sender,
            scheduled_send_date if scheduled_send_date is not None else datetime.now(),
            retry_max if retry_max is not None else self.MAX_RETRY_COUNT,
        )
        attachments = attachments or {}
        for file_name, content in attachments.items():
            await conn.execute(
                """
                INSERT INTO mail_attachments (mail_id, file_name, content)
                VALUES ($1, $2, $3)
                """,
                mail_id,
                file_name,
                content,
            )
        self.logger.debug(f"Added mail to database buffer for {to_addr}")

    @with_db_transaction(read_only=True)
    async def _fetch_mail(self, *, conn: Connection) -> list[Mail]:
        # fetch all unsent mails from nodes with email enabled that are either:
        # 1. Due for their first attempt (no retry_next_attempt)
        # 2. Due for a retry attempt (retry_next_attempt <= now)
        # 3. Under the maximum retry count

        return await conn.fetch_many(
            Mail,
            """
            select *
            from mail_with_attachments
            where send_date is null
              and (
                  (retry_next_attempt is null and scheduled_send_date <= $1)
                  or 
                  (retry_next_attempt is not null and retry_next_attempt <= $1)
              )
              and retry_count < retry_max
            """,
            datetime.now(),
        )

    async def run_mail_service(self):
        self.logger.info("Starting periodic job to send mails.")
        while True:
            try:
                await asyncio.sleep(self.MAIL_SEND_CHECK_INTERVAL.seconds)
                mails = await self._fetch_mail()
                for mail in mails:
                    await self._send_mail(mail=mail)
                    await asyncio.sleep(self.MAIL_SEND_INTERVAL.seconds)
            except Exception as e:
                self.logger.exception(f"Failed to send mail with error {e}")

    def _calculate_next_retry_time(self, retry_count: int) -> datetime:
        """Calculate the next retry time using doubling backoff pattern"""
        delay = self.BASE_RETRY_DELAY * (self.BACKOFF_FACTOR ** retry_count)
        return datetime.now() + delay

    @with_db_transaction
    async def _send_mail(
        self,
        *,
        conn: Connection,
        mail: Mail,
    ) -> None:
        self.logger.debug(f"Sending mail to {mail.to_addr}, attempt {mail.retry_count + 1}/{mail.retry_max}")
        res_config = await fetch_restricted_event_settings_for_node(conn, mail.node_id)
        smtp_config = res_config.smtp_config
        if not smtp_config:
            self.logger.info(
                f"The mail was not sent because event with node id {mail.node_id} has mail sending deactivated"
            )
            # Mark as failed without retry - configuration issue
            await conn.execute(
                """
                update mails
                set retry_count = retry_max, 
                    failure_reason = $1
                where id = $2
                """,
                "Mail sending deactivated for this event",
                mail.id,
            )
            return

        message = MIMEMultipart()
        message["Subject"] = mail.subject
        message["From"] = mail.from_addr if mail.from_addr else res_config.email_default_sender
        message["To"] = mail.to_addr
        message["Date"] = formatdate(localtime=True)

        if mail.html_message:
            # TODO: to properly handle html messages, we need to convert html to plain text
            # and add the plain text version as an alternative part
            msg = MIMEText(mail.message, "html", "utf-8")
        else:
            msg = MIMEText(mail.message, "plain", "utf-8")
        message.attach(msg)

        for attachment in mail.attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename= {attachment.file_name}")
            message.attach(part)

        try:
            assert smtp_config.smtp_host is not None and smtp_config.smtp_port is not None
            await aiosmtplib.send(
                message,
                hostname=smtp_config.smtp_host,
                port=smtp_config.smtp_port,
                username=smtp_config.smtp_username,
                password=smtp_config.smtp_password,
                start_tls=True,
            )
            self.logger.debug(f"Mail sent to {mail.to_addr}")
            
            # Mark as successfully sent
            await conn.execute(
                """
                update mails
                set send_date = $1
                where id = $2
                """,
                datetime.now(),
                mail.id,
            )
        except Exception as e:
            error_message = str(e)
            self.logger.exception(f"Failed to send mail to {mail.to_addr} with error {error_message}")
            
            # Update retry information
            new_retry_count = mail.retry_count + 1
            
            if new_retry_count >= mail.retry_max:
                # Max retries reached, mark as permanently failed
                self.logger.warning(
                    f"Mail to {mail.to_addr} (ID {mail.id}) failed permanently after {new_retry_count} attempts: {error_message}"
                )
                await conn.execute(
                    """
                    update mails
                    set retry_count = $1,
                        failure_reason = $2
                    where id = $3
                    """,
                    new_retry_count,
                    error_message,
                    mail.id,
                )
            else:
                # Schedule next retry with doubling backoff pattern
                next_retry = self._calculate_next_retry_time(new_retry_count - 1)
                self.logger.info(
                    f"Scheduling retry {new_retry_count}/{mail.retry_max} for mail to {mail.to_addr} (ID {mail.id}) at {next_retry}"
                )
                await conn.execute(
                    """
                    update mails
                    set retry_count = $1,
                        retry_next_attempt = $2,
                        failure_reason = $3
                    where id = $4
                    """,
                    new_retry_count,
                    next_retry,
                    error_message,
                    mail.id,
                )
