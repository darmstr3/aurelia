"""Caller intake data model.

This module defines the single source of truth for what Aurelia captures from
a med-spa after-hours call. The :class:`CallerIntake` model is constructed by
the agent's ``submit_intake`` tool and is the only shape that ever leaves the
LLM and reaches Google Sheets or the on-call escalation channel.
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
    "Patient Status",
    "Reason for Call",
    "Treatment / Topic",
    "Urgency",
    "Callback Window",
    "Notes",
)


class Urgency(str, Enum):  # noqa: UP042 — keep (str, Enum) for broad pydantic compatibility
    """How quickly the customer needs a callback.

    ``EMERGENCY`` triggers the on-call page; the other levels are queued for
    the morning front-desk team.
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


class PatientStatus(str, Enum):  # noqa: UP042
    """Whether the caller is already in our patient records."""

    NEW = "new"
    EXISTING = "existing"

    @classmethod
    def from_loose(cls, value: str) -> PatientStatus:
        normalized = value.strip().lower()
        if normalized in {"new", "first_time", "first-time", "prospect", "lead"}:
            return cls.NEW
        if normalized in {"existing", "current", "returning", "patient", "client"}:
            return cls.EXISTING
        raise ValueError(f"Unknown patient status: {value!r}")


class ReasonForCall(str, Enum):  # noqa: UP042
    """What the caller is calling about.

    ``POST_PROCEDURE_CONCERN`` is the bucket the on-call provider cares about
    most — anything from a slightly bruised lip to a vascular occlusion lands
    here, and the urgency level differentiates within.
    """

    POST_PROCEDURE_CONCERN = "post_procedure_concern"
    NEW_CONSULT = "new_consult"
    SCHEDULING = "scheduling"
    PRICING = "pricing"
    OTHER = "other"

    @classmethod
    def from_loose(cls, value: str) -> ReasonForCall:
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "post_procedure_concern": cls.POST_PROCEDURE_CONCERN,
            "post_procedure": cls.POST_PROCEDURE_CONCERN,
            "post_op": cls.POST_PROCEDURE_CONCERN,
            "complication": cls.POST_PROCEDURE_CONCERN,
            "concern": cls.POST_PROCEDURE_CONCERN,
            "new_consult": cls.NEW_CONSULT,
            "consult": cls.NEW_CONSULT,
            "consultation": cls.NEW_CONSULT,
            "new_patient": cls.NEW_CONSULT,
            "scheduling": cls.SCHEDULING,
            "schedule": cls.SCHEDULING,
            "reschedule": cls.SCHEDULING,
            "appointment": cls.SCHEDULING,
            "booking": cls.SCHEDULING,
            "pricing": cls.PRICING,
            "price": cls.PRICING,
            "cost": cls.PRICING,
            "quote": cls.PRICING,
            "other": cls.OTHER,
        }
        if normalized in aliases:
            return aliases[normalized]
        raise ValueError(f"Unknown reason for call: {value!r}")


_PHONE_DIGITS = re.compile(r"\d")


class CallerIntake(BaseModel):
    """A validated record of one after-hours med-spa call."""

    caller_name: str = Field(min_length=1, max_length=120)
    callback_number: str = Field(min_length=7, max_length=32)
    patient_status: PatientStatus
    reason_for_call: ReasonForCall
    treatment_of_interest: str = Field(
        min_length=1,
        max_length=240,
        description="Treatment the caller asked about or recently received "
        "(e.g. 'Botox', 'laser hair removal', 'lip filler last Tuesday').",
    )
    urgency: Urgency
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

    @field_validator("caller_name", "treatment_of_interest", "callback_window")
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

    @property
    def is_post_procedure(self) -> bool:
        return self.reason_for_call is ReasonForCall.POST_PROCEDURE_CONCERN

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
            self.patient_status.value,
            self.reason_for_call.value,
            self.treatment_of_interest,
            self.urgency.value,
            self.callback_window,
            self.notes,
        ]
