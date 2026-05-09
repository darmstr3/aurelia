"""Shared pytest fixtures.

Keeps test files focused on the behavior they cover, and ensures the cached
``get_settings()`` doesn't bleed real environment variables between tests.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from aurelia.config import Settings, get_settings
from aurelia.intake import CallerIntake, PatientStatus, ReasonForCall, Urgency


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Drop the lru_cache around get_settings between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def base_settings() -> Settings:
    """A minimal Settings object that won't accidentally hit any external system."""
    return Settings(
        aurelia_env="dev",
        aurelia_log_level="WARNING",
        google_sheets_spreadsheet_id="test-spreadsheet-id",
        google_sheets_worksheet_name="Intakes",
        escalation_enabled=True,
        escalation_email_to="oncall@example.com",
        escalation_email_from="aurelia@example.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="aurelia",
        smtp_password="hunter2",
        smtp_use_tls=True,
    )


@pytest.fixture
def sample_intake() -> CallerIntake:
    """A routine new-consult intake — no escalation expected."""
    return CallerIntake(
        caller_name="Maya Chen",
        callback_number="(555) 010-2030",
        patient_status=PatientStatus.NEW,
        reason_for_call=ReasonForCall.NEW_CONSULT,
        treatment_of_interest="laser hair removal — underarms and bikini",
        urgency=Urgency.ROUTINE,
        callback_window="after 9am tomorrow",
        notes="Has a friend who's a current patient; mentioned a referral.",
    )


@pytest.fixture
def emergency_intake() -> CallerIntake:
    """A post-procedure emergency: vision changes after under-eye filler."""
    return CallerIntake(
        caller_name="Sam Patel",
        callback_number="555-010-9999",
        patient_status=PatientStatus.EXISTING,
        reason_for_call=ReasonForCall.POST_PROCEDURE_CONCERN,
        treatment_of_interest="under-eye filler this afternoon",
        urgency=Urgency.EMERGENCY,
        callback_window="immediately",
        notes="Reporting blurred vision in the right eye and pain near the injection site.",
    )
