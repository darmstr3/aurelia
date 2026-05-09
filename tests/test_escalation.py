"""Tests for the EmergencyPager."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any, ClassVar
from unittest.mock import MagicMock

from aurelia.config import Settings
from aurelia.escalation import EmergencyPager, _build_message
from aurelia.intake import CallerIntake


class _FakeSMTP:
    """Stand-in for smtplib.SMTP that records every call.

    Each instance records what was sent so tests can assert on it. A class
    attribute ``raise_on_send`` lets a test simulate failures on demand.
    """

    raise_on_send: ClassVar[type[BaseException] | None] = None
    instances: ClassVar[list[_FakeSMTP]] = []

    def __init__(self, host: str, port: int, timeout: int | None = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_called = False
        self.login_called_with: tuple[str, str] | None = None
        self.sent_messages: list[EmailMessage] = []
        self.quit_called = False
        type(self).instances.append(self)

    def starttls(self, context: Any = None) -> tuple[int, bytes]:
        self.starttls_called = True
        return (220, b"ok")

    def login(self, user: str, password: str) -> tuple[int, bytes]:
        self.login_called_with = (user, password)
        return (235, b"ok")

    def send_message(self, msg: EmailMessage) -> dict[str, tuple[int, bytes]]:
        exc_type = type(self).raise_on_send
        if exc_type is not None:
            raise exc_type("simulated")
        self.sent_messages.append(msg)
        return {}

    def quit(self) -> tuple[int, bytes]:
        self.quit_called = True
        return (221, b"bye")


def _reset_fake() -> None:
    _FakeSMTP.instances = []
    _FakeSMTP.raise_on_send = None


class TestBuildMessage:
    def test_includes_required_fields(self, emergency_intake: CallerIntake) -> None:
        msg = _build_message(emergency_intake, sender="from@x", recipient="to@x")
        body = msg.get_content()
        assert emergency_intake.caller_name in body
        assert emergency_intake.callback_number in body
        assert emergency_intake.treatment_of_interest in body
        assert emergency_intake.patient_status.value in body
        assert emergency_intake.reason_for_call.value in body
        assert "EMERGENCY" in body
        assert msg["From"] == "from@x"
        assert msg["To"] == "to@x"
        assert "ON-CALL PAGE" in (msg["Subject"] or "")


class TestPage:
    def test_happy_path_sends_and_returns_true(
        self, base_settings: Settings, emergency_intake: CallerIntake
    ) -> None:
        _reset_fake()
        pager = EmergencyPager(settings=base_settings, smtp_factory=_FakeSMTP)  # type: ignore[arg-type]

        ok = pager.page(emergency_intake)

        assert ok is True
        assert len(_FakeSMTP.instances) == 1
        smtp = _FakeSMTP.instances[0]
        assert smtp.host == "smtp.example.com"
        assert smtp.port == 587
        assert smtp.starttls_called is True
        assert smtp.login_called_with == ("aurelia", "hunter2")
        assert len(smtp.sent_messages) == 1
        assert smtp.quit_called is True

    def test_disabled_returns_false_without_sending(
        self, base_settings: Settings, emergency_intake: CallerIntake
    ) -> None:
        _reset_fake()
        settings = base_settings.model_copy(update={"escalation_enabled": False})
        pager = EmergencyPager(settings=settings, smtp_factory=_FakeSMTP)  # type: ignore[arg-type]

        assert pager.page(emergency_intake) is False
        assert _FakeSMTP.instances == []

    def test_incomplete_smtp_config_returns_false(
        self, base_settings: Settings, emergency_intake: CallerIntake
    ) -> None:
        _reset_fake()
        settings = base_settings.model_copy(update={"smtp_host": ""})
        pager = EmergencyPager(settings=settings, smtp_factory=_FakeSMTP)  # type: ignore[arg-type]

        assert pager.page(emergency_intake) is False
        assert _FakeSMTP.instances == []

    def test_swallows_smtp_error_after_retries(
        self, base_settings: Settings, emergency_intake: CallerIntake
    ) -> None:
        _reset_fake()
        _FakeSMTP.raise_on_send = smtplib.SMTPException
        pager = EmergencyPager(settings=base_settings, smtp_factory=_FakeSMTP)  # type: ignore[arg-type]

        # Should not raise; failure path returns False.
        assert pager.page(emergency_intake) is False
        # 3 retries means 3 SMTP instances (each call opens a fresh connection).
        assert len(_FakeSMTP.instances) == 3

    def test_skip_login_when_no_username(
        self, base_settings: Settings, emergency_intake: CallerIntake
    ) -> None:
        _reset_fake()
        settings = base_settings.model_copy(update={"smtp_username": ""})
        pager = EmergencyPager(settings=settings, smtp_factory=_FakeSMTP)  # type: ignore[arg-type]

        assert pager.page(emergency_intake) is True
        assert _FakeSMTP.instances[0].login_called_with is None

    def test_skip_starttls_when_disabled(
        self, base_settings: Settings, emergency_intake: CallerIntake
    ) -> None:
        _reset_fake()
        settings = base_settings.model_copy(update={"smtp_use_tls": False})
        pager = EmergencyPager(settings=settings, smtp_factory=_FakeSMTP)  # type: ignore[arg-type]

        assert pager.page(emergency_intake) is True
        assert _FakeSMTP.instances[0].starttls_called is False


def test_real_smtplib_is_default() -> None:
    pager = EmergencyPager(settings=Settings())
    # Sanity check that we didn't accidentally bind a different default.
    assert pager._smtp_factory is smtplib.SMTP

    mock = MagicMock(spec=smtplib.SMTP)
    pager2 = EmergencyPager(settings=Settings(), smtp_factory=mock)
    assert pager2._smtp_factory is mock
