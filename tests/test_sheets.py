"""Tests for SheetsClient.

We mock the googleapiclient resource at the boundary. The client's contract
is: take a CallerIntake, hit ``spreadsheets().values().append().execute()``
once, retry on 5xx/429, fail loudly on other errors.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from aurelia.config import Settings
from aurelia.intake import CallerIntake
from aurelia.sheets import SheetsAppendError, SheetsClient


def _make_http_error(status: int) -> HttpError:
    """Build an HttpError with the given HTTP status."""
    resp = MagicMock()
    resp.status = status
    resp.reason = "test"
    return HttpError(resp=resp, content=b'{"error":"test"}')


def _service_with_append(execute_side_effect: Any) -> MagicMock:
    """Build a fake service whose append().execute() does ``execute_side_effect``.

    ``execute_side_effect`` may be a list (sequence of return values / raises)
    or a single value. MagicMock handles both.
    """
    service = MagicMock()
    append = service.spreadsheets.return_value.values.return_value.append.return_value
    if isinstance(execute_side_effect, list):
        append.execute.side_effect = execute_side_effect
    else:
        append.execute.return_value = execute_side_effect
    return service


class TestAppendIntake:
    def test_happy_path(self, base_settings: Settings, sample_intake: CallerIntake) -> None:
        service = _service_with_append({"updates": {"updatedRange": "Intakes!A2:I2"}})
        client = SheetsClient(settings=base_settings, service=service)

        result = client.append_intake(sample_intake)

        assert result["updates"]["updatedRange"] == "Intakes!A2:I2"
        append_call = service.spreadsheets.return_value.values.return_value.append
        append_call.assert_called_once()
        kwargs = append_call.call_args.kwargs
        assert kwargs["spreadsheetId"] == "test-spreadsheet-id"
        assert kwargs["range"] == "'Intakes'!A1"
        assert kwargs["body"]["values"][0] == sample_intake.to_sheets_row()

    def test_retries_on_500_then_succeeds(
        self, base_settings: Settings, sample_intake: CallerIntake
    ) -> None:
        service = _service_with_append(
            [
                _make_http_error(500),
                _make_http_error(503),
                {"updates": {"updatedRange": "Intakes!A5:I5"}},
            ]
        )
        client = SheetsClient(settings=base_settings, service=service)
        result = client.append_intake(sample_intake)
        assert "updates" in result
        # Three attempts were made.
        assert (
            service.spreadsheets.return_value.values.return_value.append.return_value.execute.call_count
            == 3
        )

    def test_retries_on_429(self, base_settings: Settings, sample_intake: CallerIntake) -> None:
        service = _service_with_append(
            [_make_http_error(429), {"updates": {"updatedRange": "Intakes!A2:I2"}}]
        )
        client = SheetsClient(settings=base_settings, service=service)
        client.append_intake(sample_intake)
        assert (
            service.spreadsheets.return_value.values.return_value.append.return_value.execute.call_count
            == 2
        )

    def test_does_not_retry_on_4xx_other_than_429(
        self, base_settings: Settings, sample_intake: CallerIntake
    ) -> None:
        service = _service_with_append([_make_http_error(403)])
        client = SheetsClient(settings=base_settings, service=service)

        with pytest.raises(SheetsAppendError):
            client.append_intake(sample_intake)

        # Only one attempt.
        assert (
            service.spreadsheets.return_value.values.return_value.append.return_value.execute.call_count
            == 1
        )

    def test_exhausts_retries_then_raises(
        self, base_settings: Settings, sample_intake: CallerIntake
    ) -> None:
        service = _service_with_append([_make_http_error(500)] * 8)
        client = SheetsClient(settings=base_settings, service=service)

        with pytest.raises(SheetsAppendError):
            client.append_intake(sample_intake)

    def test_missing_spreadsheet_id_raises(self, sample_intake: CallerIntake) -> None:
        settings = Settings(google_sheets_spreadsheet_id="")
        client = SheetsClient(settings=settings, service=MagicMock())
        with pytest.raises(SheetsAppendError, match="not configured"):
            client.append_intake(sample_intake)

    def test_network_error_is_wrapped(
        self, base_settings: Settings, sample_intake: CallerIntake
    ) -> None:
        service = _service_with_append([ConnectionError("boom")] * 8)
        client = SheetsClient(settings=base_settings, service=service)
        with pytest.raises(SheetsAppendError):
            client.append_intake(sample_intake)


class TestEnsureHeader:
    def test_writes_when_missing(self, base_settings: Settings) -> None:
        service = MagicMock()
        values = service.spreadsheets.return_value.values.return_value
        values.get.return_value.execute.return_value = {}  # empty A1
        values.update.return_value.execute.return_value = {}

        SheetsClient(settings=base_settings, service=service).ensure_header()

        values.update.assert_called_once()

    def test_skips_when_present(self, base_settings: Settings) -> None:
        service = MagicMock()
        values = service.spreadsheets.return_value.values.return_value
        values.get.return_value.execute.return_value = {"values": [["Captured At (UTC)"]]}

        SheetsClient(settings=base_settings, service=service).ensure_header()

        values.update.assert_not_called()
