"""Caller intake data model.

This module defines the single source of truth for what Aurelia captures from
a call. The :class:`CallerIntake` model is constructed by the agent's
``submit_intake`` tool and is the only shape that ever leaves the LLM and
reaches Google Sheets or the escalation channel.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator

# Sheet column order. Treated as the contract; if you change this, also update
# the header row in the target spreadsheet (or use a freshly created sheet).
SHEET_COLUMNS: tuple[str, ...] = (
    "Captured At (UTC)",
    "Call ID",
    "Caller Name",
    "Callback Number",
    "Service Address",
    "Urgency",
    "Problem Description",
    "Callback Window",
    "Notes",
)


class Urgency(str, Enum):  # noqa: UP042 — keep (str, Enum) for broad pydantic compatibility
    """How quickly the customer needs a callback.

    ``EMERGENCY`` triggers the on-call page; the other levels are queued for
    the morning office staff.
    """

    EMERGENCY = "emergency"
    URGENT = "urgent"
    ROUTINE = "routine"

    @classmethod
    def from_loose(cls, value: str) -> Urgency:
        """Parse free-form urgency hints from the LLM into a canonical level.

        The model is asked to use one of the three canonical strings, but real
        traffic will include things like ``"high"`` or ``"asap"``. We prefer
        recognizing them over rejecting the call.
        """
        normalized = value.strip().lower()
        if normalized in {"emergency", "critical", "asap", "now", "immediate"}:
            return cls.EMERGENCY
        if normalized in {"urgent", "high", "soon", "today"}:
            return cls.URGENT
        if normalized in {"routine", "normal", "standard", "low", "whenever"}:
            return cls.ROUTINE
        raise ValueError(f"Unknown urgency level: {value!r}")


_PHONE_DIGITS = re.compile(r"\d")


class CallerIntake(BaseModel):
    """A validated record of one after-hours call."""

    caller_name: str = Field(min_length=1, max_length=120)
    callback_number: str = Field(min_length=7, max_length=32)
    service_address: str = Field(min_length=1, max_length=240)
    urgency: Urgency
    problem_description: str = Field(min_length=1, max_length=2000)
    callback_window: str = Field(
        min_length=1,
        max_length=120,
        description="Free-form window the caller is reachable, e.g. 'after 8am tomorrow'.",
    )
    notes: str = Field(default="", max_length=2000)
    call_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),  # noqa: UP017 - 3.10 compat for tests
    )

    # ---- Validators ----

    @field_validator("caller_name", "service_address", "problem_description", "callback_window")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("notes")
    @classmethod
    def _strip_optional(cls, value: str) -> str:
        return value.strip()

    @field_validator("callback_number")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        cleaned = value.strip()
        digits = _PHONE_DIGITS.findall(cleaned)
        if len(digits) < 7:
            raise ValueError("callback number must contain at least 7 digits")
        return cleaned

    # ---- Behavior ----

    @property
    def is_emergency(self) -> bool:
        return self.urgency is Urgency.EMERGENCY

    def to_sheets_row(self) -> list[str]:
        """Render this intake as a row for Google Sheets append.

        Order matches :data:`SHEET_COLUMNS`. All values are strings — Sheets
        will infer types on read, but we never want a bad type to break an
        append.
        """
        return [
            self.captured_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            self.call_id,
            self.caller_name,
            self.callback_number,
            self.service_address,
            self.urgency.value,
            self.problem_description,
            self.callback_window,
            self.notes,
        ]
