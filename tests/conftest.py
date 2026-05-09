"""Shared pytest fixtures.

Keeps test files focused on the behavior they cover, and ensures the cached
``get_settings()`` doesn't bleed real environment variables between tests.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from aurelia.config import Settings, get_settings
from aurelia.intake import CallerIntake, Urgency


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
    return CallerIntake(
        caller_name="Maya Chen",
        callback_number="(555) 010-2030",
        service_address="412 Cedar St, Springfield",
        urgency=Urgency.URGENT,
        problem_description="No heat upstairs since this morning, downstairs feels cold too.",
        callback_window="after 8am tomorrow",
        notes="Two cats indoors, gate code 1492.",
    )


@pytest.fixture
def emergency_intake() -> CallerIntake:
    return CallerIntake(
        caller_name="Sam Patel",
        callback_number="555-010-9999",
        service_address="88 Oak Ave",
        urgency=Urgency.EMERGENCY,
        problem_description="Smell of gas near the furnace, kids are home.",
        callback_window="immediately",
    )
