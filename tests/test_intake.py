"""Tests for the CallerIntake model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aurelia.intake import SHEET_COLUMNS, CallerIntake, Urgency


class TestUrgency:
    def test_canonical_values_round_trip(self) -> None:
        for level in Urgency:
            assert Urgency.from_loose(level.value) is level

    @pytest.mark.parametrize(
        ("loose", "expected"),
        [
            ("EMERGENCY", Urgency.EMERGENCY),
            ("Critical", Urgency.EMERGENCY),
            ("asap", Urgency.EMERGENCY),
            ("immediate", Urgency.EMERGENCY),
            ("high", Urgency.URGENT),
            ("today", Urgency.URGENT),
            ("normal", Urgency.ROUTINE),
            ("Whenever ", Urgency.ROUTINE),
        ],
    )
    def test_loose_parsing(self, loose: str, expected: Urgency) -> None:
        assert Urgency.from_loose(loose) is expected

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown urgency"):
            Urgency.from_loose("yesterday")


class TestCallerIntake:
    def test_round_trip_minimal(self, sample_intake: CallerIntake) -> None:
        # captured_at and call_id are auto-populated.
        assert sample_intake.call_id
        assert sample_intake.captured_at.tzinfo is not None

    @pytest.mark.parametrize(
        "bad_phone",
        ["", "abc", "12345", "(   )    -    "],
    )
    def test_callback_number_must_have_seven_digits(self, bad_phone: str) -> None:
        with pytest.raises(ValidationError):
            CallerIntake(
                caller_name="x",
                callback_number=bad_phone,
                service_address="x",
                urgency=Urgency.ROUTINE,
                problem_description="x",
                callback_window="x",
            )

    def test_phone_format_preserved(self) -> None:
        intake = CallerIntake(
            caller_name="x",
            callback_number="  (555) 010-2030  ",
            service_address="x",
            urgency=Urgency.ROUTINE,
            problem_description="x",
            callback_window="x",
        )
        # Stripped of outer whitespace, otherwise unchanged.
        assert intake.callback_number == "(555) 010-2030"

    @pytest.mark.parametrize(
        "field",
        ["caller_name", "service_address", "problem_description", "callback_window"],
    )
    def test_required_string_fields_reject_blank(self, field: str) -> None:
        kwargs = {
            "caller_name": "x",
            "callback_number": "555-010-2030",
            "service_address": "x",
            "urgency": Urgency.ROUTINE,
            "problem_description": "x",
            "callback_window": "x",
        }
        kwargs[field] = "   "
        with pytest.raises(ValidationError):
            CallerIntake(**kwargs)

    def test_is_emergency(self, emergency_intake: CallerIntake) -> None:
        assert emergency_intake.is_emergency is True

    def test_to_sheets_row_matches_columns(self, sample_intake: CallerIntake) -> None:
        row = sample_intake.to_sheets_row()
        assert len(row) == len(SHEET_COLUMNS)
        # All values stringified — no None, no datetime objects, etc.
        assert all(isinstance(v, str) for v in row)

    def test_to_sheets_row_field_order(self, sample_intake: CallerIntake) -> None:
        row = sample_intake.to_sheets_row()
        # Spot-check that the values land in the contracted positions.
        assert row[1] == sample_intake.call_id
        assert row[2] == sample_intake.caller_name
        assert row[5] == sample_intake.urgency.value
        assert row[6] == sample_intake.problem_description
        assert "UTC" in row[0]

    def test_notes_default_empty(self) -> None:
        intake = CallerIntake(
            caller_name="x",
            callback_number="555-010-2030",
            service_address="x",
            urgency=Urgency.ROUTINE,
            problem_description="x",
            callback_window="x",
        )
        assert intake.notes == ""
