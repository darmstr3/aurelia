"""Google Sheets append client for caller intakes.

Wraps the Google Sheets v4 API with the bare minimum we need: service-account
auth, a single ``append_intake`` method, a header bootstrap helper, and
exponential-backoff retry on transient errors.

Designed to be cheap to instantiate (auth is lazy) and easy to mock — every
network call goes through ``self._service.spreadsheets()`` which tests can
substitute.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from aurelia.config import Settings, get_settings
from aurelia.intake import SHEET_COLUMNS, CallerIntake
from aurelia.logging import get_logger

_log = get_logger(__name__)
_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


class SheetsAppendError(RuntimeError):
    """Raised when an intake could not be appended after all retries."""


def _is_transient_http_error(exc: BaseException) -> bool:
    """Retry only on 5xx and rate-limit responses; let 4xx fail fast."""
    if isinstance(exc, HttpError):
        status = getattr(exc.resp, "status", 0)
        try:
            status_int = int(status)
        except (TypeError, ValueError):
            return False
        return status_int == 429 or status_int >= 500
    # Network blips, DNS hiccups, broken pipes, etc.
    return isinstance(exc, ConnectionError | TimeoutError | OSError)


class _SheetsService(Protocol):
    """Minimal slice of the googleapiclient resource we actually use.

    Lets tests substitute a duck-typed fake without importing the SDK.
    """

    def spreadsheets(self) -> Any: ...


def _build_credentials(settings: Settings) -> service_account.Credentials:
    """Load service-account credentials from inline JSON or a file path.

    Inline JSON wins because it's the production path on Render — they don't
    let us mount files easily, so we ship the key as an env var.
    """
    inline = settings.google_service_account_json.get_secret_value()
    if inline:
        try:
            info = json.loads(inline)
        except json.JSONDecodeError as exc:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc
        creds = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
            info, scopes=list(_SCOPES)
        )
        return creds  # type: ignore[no-any-return]

    file_path = settings.google_service_account_file
    if file_path is None:
        raise ValueError(
            "No Google credentials configured: set GOOGLE_SERVICE_ACCOUNT_JSON "
            "or GOOGLE_SERVICE_ACCOUNT_FILE."
        )
    creds = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
        str(Path(file_path)), scopes=list(_SCOPES)
    )
    return creds  # type: ignore[no-any-return]


class SheetsClient:
    """Client for appending caller intakes to a Google Sheet.

    Auth is deferred until the first API call so importing this module is
    side-effect-free and tests don't need credentials.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        service: _SheetsService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._service: _SheetsService | None = service
        self._spreadsheet_id = self._settings.google_sheets_spreadsheet_id.strip()
        # Strip whitespace/CR — .env editors sometimes save CRLF and a trailing
        # \r in the sheet name produces "Unable to parse range" from the API.
        self._worksheet = self._settings.google_sheets_worksheet_name.strip()

    def _range(self, cell: str) -> str:
        """Build a Sheets API range. Sheet name is single-quoted for safety
        (handles spaces, apostrophes, and odd characters without changing the
        call sites)."""
        escaped = self._worksheet.replace("'", "''")
        return f"'{escaped}'!{cell}"

    # ---- Internals ----

    def _get_service(self) -> _SheetsService:
        if self._service is None:
            creds = _build_credentials(self._settings)
            # cache_discovery=False avoids file-system caching that warns on
            # newer google-api-python-client when oauth2client isn't present.
            self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    @retry(
        retry=retry_if_exception(_is_transient_http_error),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        reraise=True,
    )
    def _append_row(self, row: list[str]) -> dict[str, Any]:
        sheets = self._get_service().spreadsheets()
        request = sheets.values().append(
            spreadsheetId=self._spreadsheet_id,
            range=self._range("A1"),
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        )
        response: dict[str, Any] = request.execute()
        return response

    # ---- Public API ----

    def append_intake(self, intake: CallerIntake) -> dict[str, Any]:
        """Append an intake row, retrying transient failures.

        Raises:
            SheetsAppendError: when retries are exhausted or the error is
                fatal (4xx other than 429, malformed config, etc.). The
                original exception is chained.
        """
        if not self._spreadsheet_id:
            raise SheetsAppendError("GOOGLE_SHEETS_SPREADSHEET_ID is not configured")

        log = _log.bind(call_id=intake.call_id, urgency=intake.urgency.value)
        try:
            response = self._append_row(intake.to_sheets_row())
        except RetryError as exc:  # pragma: no cover - tenacity reraises; defensive
            log.error("sheets.append_failed", error=str(exc))
            raise SheetsAppendError("retries exhausted") from exc
        except HttpError as exc:
            log.error(
                "sheets.append_failed",
                error=str(exc),
                status=getattr(exc.resp, "status", "unknown"),
            )
            raise SheetsAppendError(f"sheets API error: {exc}") from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            log.error("sheets.append_failed", error=str(exc))
            raise SheetsAppendError(f"network error: {exc}") from exc

        log.info(
            "sheets.append_ok",
            updated_range=response.get("updates", {}).get("updatedRange"),
        )
        return response

    def ensure_header(self) -> None:
        """Write the header row if cell A1 is empty.

        Convenience for first-time setup. Idempotent: a non-empty A1 is left
        alone, even if its values don't match :data:`SHEET_COLUMNS` — we don't
        want to overwrite anything the user has customized.
        """
        sheets = self._get_service().spreadsheets()
        result = (
            sheets.values()
            .get(spreadsheetId=self._spreadsheet_id, range=self._range("A1:A1"))
            .execute()
        )
        existing = result.get("values") or []
        if existing and existing[0]:
            _log.debug("sheets.header_exists")
            return
        sheets.values().update(
            spreadsheetId=self._spreadsheet_id,
            range=self._range("A1"),
            valueInputOption="USER_ENTERED",
            body={"values": [list(SHEET_COLUMNS)]},
        ).execute()
        _log.info("sheets.header_written")
