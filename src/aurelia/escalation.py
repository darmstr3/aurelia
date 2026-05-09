"""Emergency paging for after-hours med-spa calls.

When :class:`~aurelia.intake.CallerIntake` comes in with
``urgency == EMERGENCY`` we send an email page to the on-call provider. We
deliberately keep this synchronous and stdlib-only — fewer moving parts means
fewer failure modes during an actual emergency.

Failures here are logged but never raised back to the caller flow: a missed
page is bad, but a missed page that *also* breaks the call and prevents the
intake from landing in Sheets is worse. The on-call team has Sheets access
as a backstop.
"""

from __future__ import annotations

import contextlib
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from aurelia.config import Settings, get_settings
from aurelia.intake import CallerIntake
from aurelia.logging import get_logger

_log = get_logger(__name__)


class _SMTPSender(Protocol):
    """Slice of smtplib we use, so tests can substitute a fake.

    Mirrors :class:`smtplib.SMTP` enough for ``send_message``.
    """

    def starttls(self, context: ssl.SSLContext | None = ...) -> tuple[int, bytes]: ...
    def login(self, user: str, password: str) -> tuple[int, bytes]: ...
    def send_message(self, msg: EmailMessage) -> dict[str, tuple[int, bytes]]: ...
    def quit(self) -> tuple[int, bytes]: ...


def _build_message(intake: CallerIntake, *, sender: str, recipient: str) -> EmailMessage:
    """Format the on-call page email."""
    msg = EmailMessage()
    msg["Subject"] = (
        f"[ON-CALL PAGE] Med-spa {intake.urgency.value}: {intake.caller_name} — "
        f"{intake.treatment_of_interest}"
    )
    msg["From"] = sender
    msg["To"] = recipient
    body = (
        f"Aurelia after-hours intake just captured an emergency call.\n"
        f"\n"
        f"Caller:        {intake.caller_name}\n"
        f"Callback #:    {intake.callback_number}\n"
        f"Patient:       {intake.patient_status.value}\n"
        f"Reason:        {intake.reason_for_call.value}\n"
        f"Treatment:     {intake.treatment_of_interest}\n"
        f"Urgency:       {intake.urgency.value.upper()}\n"
        f"Best window:   {intake.callback_window}\n"
        f"\n"
        f"Caller's words:\n"
        f"{intake.notes or '(no additional notes)'}\n"
    )
    body += (
        f"\n--\nCall ID:       {intake.call_id}\nCaptured at:   {intake.captured_at.isoformat()}\n"
    )
    msg.set_content(body)
    return msg


class EmergencyPager:
    """Sends emergency pages over SMTP.

    Stateless — safe to instantiate per-call. The SMTP connection is opened
    fresh for each page so a stale connection from hours of idle doesn't bite
    us when we actually need it.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        smtp_factory: type[smtplib.SMTP] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        # Tests inject a stub class here; production uses smtplib.SMTP.
        self._smtp_factory: type[smtplib.SMTP] = smtp_factory or smtplib.SMTP

    @retry(
        retry=retry_if_exception_type((smtplib.SMTPException, ConnectionError, OSError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    def _send(self, msg: EmailMessage) -> None:
        s = self._settings
        smtp = self._smtp_factory(s.smtp_host, s.smtp_port, timeout=10)
        try:
            if s.smtp_use_tls:
                smtp.starttls(context=ssl.create_default_context())
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
            smtp.send_message(msg)
        finally:
            with contextlib.suppress(smtplib.SMTPException):
                smtp.quit()

    def page(self, intake: CallerIntake) -> bool:
        """Send the page. Returns True on success, False on permanent failure.

        Never raises: the call flow keeps going regardless so the intake still
        reaches Sheets. The on-call team has Sheets access as a backstop.
        """
        s = self._settings
        log = _log.bind(call_id=intake.call_id)

        if not s.escalation_enabled:
            log.info("escalation.skipped", reason="disabled_by_config")
            return False
        if not (s.smtp_host and s.escalation_email_to and s.escalation_email_from):
            log.error("escalation.skipped", reason="incomplete_smtp_config")
            return False

        msg = _build_message(
            intake, sender=s.escalation_email_from, recipient=s.escalation_email_to
        )
        try:
            self._send(msg)
        except RetryError as exc:  # pragma: no cover - reraise=True bubbles inner
            log.error("escalation.failed", error=str(exc))
            return False
        except (smtplib.SMTPException, ConnectionError, OSError) as exc:
            log.error("escalation.failed", error=str(exc))
            return False

        log.warning("escalation.paged", recipient=s.escalation_email_to)
        return True
