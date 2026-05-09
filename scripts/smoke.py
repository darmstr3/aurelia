"""Manual smoke test for the data plane.

Run after filling in `.env` to verify Google Sheets credentials and
optional SMTP credentials, *without* touching LiveKit. Useful for
isolating which side of the stack is broken when an end-to-end call
doesn't behave.

Usage:
    uv run python scripts/smoke.py            # routine intake (Sheets only)
    uv run python scripts/smoke.py --emergency  # also fires the page email
    uv run python scripts/smoke.py --header   # also bootstraps the header row
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from aurelia.config import get_settings
from aurelia.escalation import EmergencyPager
from aurelia.intake import CallerIntake, Urgency
from aurelia.logging import configure
from aurelia.sheets import SheetsAppendError, SheetsClient


def _make_intake(emergency: bool) -> CallerIntake:
    return CallerIntake(
        caller_name="Smoke Test (auto)",
        callback_number="555-010-0000",
        service_address="123 Test Lane",
        urgency=Urgency.EMERGENCY if emergency else Urgency.ROUTINE,
        problem_description=("Smoke test from scripts/smoke.py. Safe to delete this row."),
        callback_window=f"sent at {datetime.now(timezone.utc).isoformat()}",  # noqa: UP017
        notes="If you see this in production, someone ran the smoke script.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--emergency",
        action="store_true",
        help="Mark the intake as EMERGENCY and trigger the page email.",
    )
    parser.add_argument(
        "--header",
        action="store_true",
        help="Bootstrap the header row before appending.",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure(env=settings.aurelia_env, level=settings.aurelia_log_level)

    intake = _make_intake(emergency=args.emergency)
    sheets = SheetsClient(settings=settings)

    if args.header:
        print(">> ensuring header row...")
        try:
            sheets.ensure_header()
        except Exception as exc:
            print(f"!! header check failed: {exc}", file=sys.stderr)
            return 1

    print(f">> appending intake (call_id={intake.call_id}, urgency={intake.urgency.value})...")
    try:
        sheets.append_intake(intake)
    except SheetsAppendError as exc:
        print(f"!! sheets append failed: {exc}", file=sys.stderr)
        return 2
    print("ok: intake appended to Google Sheets.")

    if args.emergency:
        print(">> sending emergency page email...")
        pager = EmergencyPager(settings=settings)
        if pager.page(intake):
            print(f"ok: page email sent to {settings.escalation_email_to}.")
        else:
            print(
                "!! page email did not send (check SMTP_HOST / "
                "ESCALATION_EMAIL_* / ESCALATION_ENABLED).",
                file=sys.stderr,
            )
            return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
