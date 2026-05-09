# Aurelia

After-hours AI intake agent for a residential HVAC company. Handles overflow calls when the office is closed: greets the caller, captures a structured intake (name, callback number, problem, urgency, service address, callback window), writes the record to Google Sheets, and pages the on-call tech if it's an emergency.

> **Status:** under active development. This is a portfolio piece showing production-grade engineering practices around a real voice-agent use case.

[![CI](https://github.com/USER/aurelia/actions/workflows/ci.yml/badge.svg)](https://github.com/USER/aurelia/actions/workflows/ci.yml)

## Stack

- **Python 3.11**, [`uv`](https://docs.astral.sh/uv/) for dependency and env management
- **[LiveKit Agents](https://docs.livekit.io/agents/) 1.5** for the realtime voice loop
- **OpenAI** for the LLM and TTS, **Deepgram** for STT, **Silero** for VAD
- **Google Sheets API** as the intake of record
- **Pydantic Settings** for typed config, **structlog** for structured logs
- **Pytest**, **Ruff**, **mypy** with **GitHub Actions** CI
- **Render** for deploy

## Architecture at a glance

```
caller → SIP trunk → LiveKit room ─▶ AgentSession
                                     ├─ Deepgram STT
                                     ├─ OpenAI LLM (with submit_intake tool)
                                     ├─ OpenAI TTS
                                     └─ Silero VAD
                                          │
                            submit_intake │ (validated CallerIntake)
                                          ▼
                                    sheets.append_intake (with retry)
                                          │
                                if emergency ▼
                                    escalation.page_oncall (SMTP)
```

## Project layout

```
src/aurelia/
├── config.py       Pydantic Settings, env loading, secret handling
├── logging.py      structlog setup (dev console / prod JSON)
├── intake.py       CallerIntake model + Urgency enum + sheets row contract
├── prompts.py      System prompt + greeting builders
├── sheets.py       Google Sheets append client with retry
├── escalation.py   SMTP emergency pager (never raises into the call flow)
├── agent.py        LiveKit AgentSession + submit_intake function tool
└── cli.py          aurelia [dev|connect|start] entrypoint
tests/              Mocked unit tests for everything above
```

## Running locally

```bash
# 1. Install deps
uv sync --all-extras

# 2. Configure env
cp .env.example .env
# fill in LIVEKIT_*, OPENAI_API_KEY, DEEPGRAM_API_KEY, GOOGLE_SHEETS_*, SMTP_*

# 3. Bootstrap the spreadsheet header row (one-time)
uv run python -c "from aurelia.sheets import SheetsClient; SheetsClient().ensure_header()"

# 4. Run the agent in dev mode (connects to LiveKit and waits for a room)
uv run aurelia dev
```

To talk to the agent, join the LiveKit room from the [LiveKit Sandbox](https://agents-playground.livekit.io/) or wire up a SIP trunk (see *Phone setup* below).

## Tests, lint, types

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

## Phone setup (LiveKit SIP)

To take real calls you need a phone number that routes to a LiveKit SIP trunk. Quick path with Twilio:

1. Buy a Twilio number; create an Elastic SIP Trunk pointing at LiveKit's SIP origination URI.
2. In LiveKit, create a SIP inbound trunk and a dispatch rule that routes calls into a room with a known prefix (e.g. `aurelia-`). The agent worker watches every room matching the dispatch rule.
3. Set `LIVEKIT_*` in `.env` and run `uv run aurelia start`.

LiveKit's docs walk through the exact REST calls; see <https://docs.livekit.io/sip/>.

## Deploying

The repo includes `render.yaml`. Push to GitHub, click *New → Blueprint* on Render, point it at the repo, and fill in the secrets the blueprint marks as `sync: false`. The agent runs as a long-lived worker that holds a connection to LiveKit Cloud.

## Design notes

- **Intake is the contract.** Everything funnels into a single Pydantic `CallerIntake` model, validated before it ever leaves the agent. The model owns the Sheets row layout via `to_sheets_row()`; the LLM never picks the column order.
- **The LLM has exactly one side-effecting tool.** `submit_intake` is the only way the agent writes anything. Easier to reason about, easier to test, and a duplicate-call guard means the model can re-mention "I've recorded that" without firing two writes.
- **External services are mocked in tests.** `SheetsClient` accepts an injected service; `EmergencyPager` accepts an injected SMTP factory. The call flow is tested by exercising `submit_intake` against those fakes — no LiveKit room required.
- **Failures degrade in the right direction.** Sheets retries on 5xx/429 with exponential backoff; on permanent failure the agent apologizes and tells the caller to call back during business hours. The pager *never* raises — a missed page must not also drop the intake row.
- **Logs are structured from day one.** `structlog` with key-value events. JSON in production for ingestion; pretty console renderer in dev.

## Open work before the demo

The code-side build is done. What's left is bringing-up:

1. Push to GitHub (`gh repo create aurelia --public --source . --remote origin --push`) so CI runs.
2. Create the Google service-account key, share the Sheet with its email, and run `ensure_header()` to seed the header row.
3. Provision a LiveKit project + SIP trunk + phone number; verify dispatch routing.
4. Connect the GitHub repo on Render, paste secrets, deploy.
5. Place a real call to the number and confirm: row in Sheets, page email received for an emergency.
6. Capture the demo recording + Sheets screenshot for this README.

## What I'd do differently next time

_(filled in after the live demo)_

## Demo

_(link to recorded call + screenshot of the resulting Sheets row, after end-to-end test)_
