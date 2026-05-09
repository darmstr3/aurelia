# Deploying Aurelia

End-to-end bring-up: from fresh accounts to a public link a recruiter can click and talk to the agent. ~90 minutes the first time.

## What you'll have at the end

A LiveKit Agents Playground URL like
`https://agents-playground.livekit.io/?roomName=aurelia-...`
that anyone can open, click *Connect*, and have a real conversation with Aurelia. Every captured intake lands in your Google Sheet within seconds, and emergency-flagged calls fire an email page.

## Standing costs

| Thing                       | What it costs        | Why                                        |
| --------------------------- | -------------------- | ------------------------------------------ |
| Render starter worker       | $7 / month           | Always-on; free tier sleeps after 15 min   |
| LiveKit Cloud free tier     | $0                   | 10K minutes/month is plenty for a demo     |
| OpenAI API                  | ~$0.05 / 5-min call  | gpt-4o-mini LLM + gpt-4o-mini-tts          |
| Deepgram API                | ~$0.03 / 5-min call  | Nova-3 STT                                 |
| Google Sheets API           | $0                   | Free quota covers thousands of writes/day  |
| Gmail SMTP for paging       | $0                   | App password on a normal Gmail account     |

**Realistic monthly bill if you do 20 demos:** ~$10. Most of that is the Render worker.

## Prerequisites

You'll need accounts at:
- LiveKit Cloud (`livekit.io` → sign up, free)
- OpenAI (`platform.openai.com`, billing set up)
- Deepgram (`deepgram.com`, $200 free credit on signup)
- Google Cloud (`console.cloud.google.com`)
- Render (`render.com`)
- GitHub (the repo to point Render at)

A Gmail account for the on-call page email is fine; create an [app password](https://myaccount.google.com/apppasswords) under that account.

## Step 1: Google Sheet + service account

1. **Create a Google Sheet** for the intake records. Name it whatever you want; copy the spreadsheet ID from the URL — the long string between `/d/` and `/edit`.
2. **Create a service account.** In Google Cloud Console: *IAM & Admin* → *Service Accounts* → *Create Service Account*. Name it `aurelia-sheets`. Skip the optional role grants. After creation, click into it → *Keys* → *Add key* → *Create new key* → JSON. Save the downloaded file.
3. **Enable the Sheets API.** *APIs & Services* → *Library* → search "Google Sheets API" → *Enable*.
4. **Share the sheet with the service account.** Open the JSON file you downloaded; copy the `client_email` value (looks like `aurelia-sheets@<project>.iam.gserviceaccount.com`). Back in the Google Sheet, click *Share*, paste the email, give it *Editor* access.

## Step 2: API keys

Collect:
- **OpenAI:** `platform.openai.com/api-keys` → *Create new secret key*. Make sure billing is set up.
- **Deepgram:** `console.deepgram.com` → *API Keys* → *Create*. Default scopes are fine.
- **LiveKit Cloud:** create a new project. From *Settings* → *Keys*, grab the URL (`wss://...livekit.cloud`), API key, and API secret.
- **Gmail app password:** `myaccount.google.com/apppasswords`. Use this as `SMTP_PASSWORD`; SMTP host is `smtp.gmail.com`, port `587`.

## Step 3: Local end-to-end test

Before you push to Render, run the full stack locally so you know your credentials work.

```bash
cd ~/Documents/Claude/Projects/Aurelia/Aurelia
uv sync --all-extras
cp .env.example .env
# Open .env and fill in everything from Step 2 plus GOOGLE_SHEETS_SPREADSHEET_ID
# and the path to the service-account JSON you downloaded.
```

Probe the data plane first:

```bash
uv run python scripts/smoke.py --header           # bootstraps header row + appends one routine intake
uv run python scripts/smoke.py --emergency        # fires the on-call page email
```

You should see two new rows in the sheet and one email at the on-call address. If either fails, fix that before continuing — Render won't fix credential bugs for you.

Now run the agent locally and talk to it through the LiveKit Playground:

```bash
uv run aurelia dev
```

Open <https://agents-playground.livekit.io/>, sign in with the same LiveKit account, and click *Connect*. You should hear the greeting within ~2 seconds. Walk through a routine intake (e.g. "I'd like to book a Botox consult"); confirm the row lands in the sheet.

Run one emergency intake too — say something like "I had under-eye filler this afternoon and now my vision is blurry." Confirm the urgency gets flagged EMERGENCY and the page email fires.

If both work locally, the code-side is good and the rest is just hosting.

## Step 4: Push to GitHub

```bash
gh repo create aurelia --public --source . --remote origin --push
```

If `.git.broken/` is still in the working tree from earlier setup, `rm -rf .git.broken` first.

CI runs on push — wait for the green check before continuing. If something fails, fix it locally and push again rather than ignoring it.

## Step 5: Render blueprint

1. In the Render dashboard, click *New* → *Blueprint*.
2. Connect the GitHub repo. Render reads `render.yaml` and proposes one worker service.
3. *Apply Blueprint*. The build will fail or stall on first run because secrets aren't set yet — that's expected.
4. Open the new worker → *Environment*. Fill in every env var marked `sync: false` from `.env.example`:
   - `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
   - `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`
   - `GOOGLE_SERVICE_ACCOUNT_JSON` — paste the **entire contents** of the JSON file as one string. Render handles the newlines fine.
   - `GOOGLE_SHEETS_SPREADSHEET_ID`
   - `ESCALATION_EMAIL_TO`, `ESCALATION_EMAIL_FROM`, `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`
   - `AURELIA_COMPANY_NAME`, `AURELIA_BUSINESS_HOURS`
5. *Save & Redeploy*. Watch the build log — you should see `pip install`, then `python -m livekit.agents download-files` finishing with `done`.
6. Once the worker is *Live*, check the runtime logs. You should see a structlog line like `"event": "worker.registered"` from the LiveKit SDK confirming the agent is registered with LiveKit Cloud.

## Step 6: Make a demo link

LiveKit's playground takes a `roomName` query param that pre-populates the room. Use any prefix matching your dispatch rule (default `aurelia-`):

```
https://agents-playground.livekit.io/?roomName=aurelia-demo-1
```

Click it; click *Connect*. The Render worker picks up the room within a second or two, you hear the greeting, and you can talk.

> **Important:** the playground requires the visitor to be signed into a LiveKit account that has access to your project. If you want a *truly* public link (recruiter doesn't have a LiveKit account), generate a guest token and use a custom playground URL. See LiveKit docs → "Token Generation". For a portfolio piece this isn't usually needed — most recruiters who take the time to click a demo link are fine signing up for free for 30 seconds.

## Reliability checklist before sharing the link

Run through this once before you put the link on your resume or send it to a recruiter:

- [ ] Render worker shows *Live* in the dashboard, no recent restarts.
- [ ] `uv run python scripts/smoke.py --emergency --header` from your laptop succeeds (this hits prod Sheets and SMTP).
- [ ] Open the playground link yourself, run a 30-second routine intake, confirm a row lands.
- [ ] Run an emergency intake, confirm both the row and the page email.
- [ ] (Optional) Sign up for [UptimeRobot](https://uptimerobot.com); add a keyword monitor on the LiveKit Cloud dashboard URL or the Render service URL. Free tier is fine.
- [ ] Capture a 60-second Loom showing one full intake, in case the day someone tries the link OpenAI is having an outage.

## Adding a real phone number (optional)

When you're ready to put a phone number on your resume:

1. Sign up for Twilio. Verify your address (required to buy US numbers). Add billing.
2. Buy a US local number — `~$1.15/month`. Make sure *Voice* capability is enabled.
3. In Twilio: *Elastic SIP Trunking* → create trunk → *Origination* tab → set the URI to the SIP origination URI from your LiveKit project (*Settings* → *SIP*).
4. In LiveKit, create an inbound SIP trunk and a dispatch rule that routes calls to a room with the `aurelia-` prefix. The CLI commands are in <https://docs.livekit.io/sip/quickstart/>.
5. Wire the Twilio number to the SIP trunk. Test by calling the number — you should be in a room within ~2 seconds and hear the greeting.

Add the number to your README. Done.

## Common gotchas

- **Render build OOM** during `pip install` of `livekit-plugins-turn-detector` (~2 GB of transformers weights at build time only). The starter plan is 512 MB. If this hits you, upgrade temporarily to *Standard* for the build, then downgrade. Or set `RENDER_BUILD_DOCKER=true` and use a more memory-efficient image. Most people don't see this — Render's build runners typically have more RAM than the runtime container.
- **Sheets append fails with `403 caller does not have storage.objects.create access`** — you forgot to share the spreadsheet with the service account email. Fix in step 1.4.
- **Gmail SMTP fails with "Username and Password not accepted"** — you used your real Gmail password instead of an app password. App passwords are at `myaccount.google.com/apppasswords`.
- **Agent connects but goes silent** after the greeting — check logs for OpenAI 401. The `OPENAI_API_KEY` env var is wrong or the account has no billing.
- **First call is slow** with a long pause before the greeting — the model files didn't pre-download at build time. Confirm `python -m livekit.agents download-files` ran in the build log.

## What to put on your resume

Two patterns work well:

> **Aurelia — voice agent for medical-spa after-hours intake** ([demo](your-playground-link), [code](github.com/you/aurelia)) · LiveKit Agents · Python 3.11
> Built a production voice intake agent on LiveKit + OpenAI + Deepgram with Pydantic-validated structured output to Google Sheets and on-call paging for emergencies. CI, type checks, structured logging, deployed on Render.

If you add a phone number later, replace the demo link with `(555) 555-0100` and write *"call to talk to it."* That gets clicks.
