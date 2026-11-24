# Configuration

MeetPact reads environment variables, or a `.env` file in the repository root (copy
`.env.example`). Only two things are needed for real meetings: a MeetStream key, and a Claude or
Gemini key. Everything else has a working default. Settings that people change day to day (bot name,
consent wording, sharing defaults, delivery, retention) live in **Admin → Bot & settings**.

## Required

| Variable | Purpose |
|---|---|
| `MEETSTREAM_API_KEY` | Sends bots and creates stand-up voice agents. From [app.meetstream.ai](https://app.meetstream.ai/api-key). |
| `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` | Transcript analysis and Ask. Set one. |

## Server

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/data/tracker.db` | Any SQLAlchemy URL. Postgres needs a driver such as `psycopg`. |
| `SECRET_KEY` | generated | Signs session cookies. Generated when empty and stored beside the SQLite database (`backend/data/`, or the `/data` volume in Docker). |
| `PUBLIC_URL` | - | Address MeetStream uses to reach the backend, if it must differ from `APP_URL`. Empty: `APP_URL` when it is public, else the automatic tunnel. |
| `TUNNEL` | `auto` | Without `PUBLIC_URL`, start a Cloudflare quick tunnel automatically when `cloudflared` is installed. `off` disables it. Only MeetStream's paths are reachable through it. |
| `CLOUDFLARED_PATH` | - | Path to `cloudflared` if it isn't on `PATH`. |
| `PORT` | `8000` | Port the backend listens on (the tunnel points here). |
| `APP_URL` | `http://localhost:5173` | The address people open MeetPact at. On a server, your domain (`https://meetpact.example.com`): report links, Google sign-in and MeetStream callbacks follow from it. On localhost, links are left out of Slack and email. See [self-hosting](self-hosting.md). |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS origin for the dev UI. |
| `TIMEZONE` | `UTC` | Default timezone for new schedules (IANA name). |
| `BACKGROUND_WORKERS` | `true` | Scheduler, bot watcher, calendar sync and housekeeping loops. |

## Public URL

MeetStream needs to reach MeetPact during a call for live webhooks and for the stand-up host to see
who is in the call and leave when it is done. You have three options:

0. **On a server:** set `APP_URL` to your domain and you're done ([self-hosting](self-hosting.md)).
1. **On a laptop, automatic (default):** install [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
   (`winget install Cloudflare.cloudflared`, `brew install cloudflared`, …). MeetPact starts a quick
   tunnel on startup and uses its address. Only `/api/webhooks/*`, `/api/agent/*`, `/mcp` and
   `/api/health` are reachable through it; sign-in, the UI and the rest of the API stay local.
2. **Your own tunnel or proxy:** set `PUBLIC_URL` to an HTTPS address that forwards to the backend.
3. **None** (`TUNNEL=off`, no `PUBLIC_URL`): everything works by polling; the stand-up host leaves
   60 s after everyone else has left instead of right after its goodbye, and does not see who is in
   the call.

## Bots

| Variable | Default | Purpose |
|---|---|---|
| `BOT_NAME` | `MeetPact AI Notetaker` | Name shown in the meeting (also editable in Admin). |
| `TRANSCRIPT_PROVIDER` | `meetstream` | Post-call transcription: `meetstream`, `deepgram` or `assemblyai`. Some need the provider key added on MeetStream. |
| `TRANSCRIPT_LANGUAGE` | `en` | `auto` lets the `meetstream` provider detect it. |
| `RETENTION_HOURS` | `168` | How long MeetStream keeps the recording. |
| `WAITING_ROOM_TIMEOUT` | `600` | Seconds to wait to be admitted. |
| `EVERYONE_LEFT_TIMEOUT` | `120` | Seconds to stay after everyone else leaves. |
| `NO_ONE_JOINED_TIMEOUT` | `600` | Seconds an admitted bot waits for anyone else to join, e.g. a late host. MeetStream accepts 60 to 1800. |
| `GOOGLE_BOT_LOGIN_DOMAIN` | - | Google Meet bots join signed in to an account on this Google Workspace domain instead of as a guest. See *Signed-in Google Meet bot* below. |
| `GOOGLE_BOT_SIGN_IN_EMAIL` | - | Always use this bot account; put it on the calendar invites. |
| `GOOGLE_BOT_STRICT_EMAIL` | `true` | With `GOOGLE_BOT_SIGN_IN_EMAIL`: fail if that account is busy, rather than use another one from the domain. |
| `IN_CALL_RECORDING_TIMEOUT` | `14400` | Maximum recording length (MeetStream minimum: 600). |
| `SCHEDULE_LEAD_MINUTES` | `10` | How far ahead scheduled meetings are booked with MeetStream (`join_at`). |
| `EARLY_JOIN_MINUTES` | `2` | Scheduled and calendar bots join this many minutes before the start time. MeetStream only reports people who join after the bot. A [signed-in bot](#signed-in-google-meet-bot) gets in first, so the stand-up host asks only the people present. A guest bot has to be let in by someone already there, so the host asks the people it saw join, in that order, then the rest of the team. `0` joins on time. |
| `MEETSTREAM_WEBHOOK_SECRET` | - | Verifies signed workspace webhooks. |

### Signed-in Google Meet bot

A guest bot waits in the lobby until someone admits it, so it never gets in if the host does not
come. A bot signed in to a Google account joins without knocking when:

* its email is a guest on the calendar invite, and
* the meeting's access is *Trusted* or *Restricted*, and
* the waiting room is off (with it on, a signed-in bot waits too).

Setup is done once, on Google and MeetStream (see MeetStream's *Google signed-in bots* guide):

1. Create a Google Workspace domain that holds only bot accounts, for example `bots.example.com`
   with `notetaker@bots.example.com`. A personal Gmail address cannot be used.
2. Point that domain's single sign-on at MeetStream as the SAML identity provider, with a key and
   certificate pair. No passwords are stored.
3. Register the domain and the account with MeetStream (`POST /google-login-domains`,
   `POST /google-logins`).
4. Set `GOOGLE_BOT_LOGIN_DOMAIN` (and usually `GOOGLE_BOT_SIGN_IN_EMAIL`) and restart.

Then add the bot's email to the meetings' calendar invites. Only Google Meet links are affected.
The bot's name and photo come from its Google account, not `BOT_NAME`. If signing in fails the bot
does not fall back to a guest join: the meeting shows *Failed* with the reason MeetStream gave.

Without a bot domain, the other way in is the meeting itself: in Google Meet's host controls, turn
the waiting room off and set access to *Open*, where your account offers it.

## AI analysis

| Variable | Default | Purpose |
|---|---|---|
| `ANALYSIS_PROVIDER` | auto | `gemini`, `anthropic` (Claude), `openai` or `xai` (Grok). Empty: the first one with a key (Claude, Gemini, OpenAI, Grok). Also set in the setup guide. |
| `ANALYSIS_MODEL` | `claude-opus-5-5` | Claude model. |
| `ANALYSIS_EFFORT` | `high` | Claude effort level. |
| `GEMINI_MODEL` | `gemini-2.5-pro` | Gemini model. `gemini-3.8-flash` is faster. |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | - / `gpt-5` | OpenAI for the notes (chat completions with JSON-schema output). Use a model your key can call; the setup guide's check lists close matches. |
| `XAI_API_KEY` / `XAI_MODEL` | - / `grok-4` | Grok (xAI) for the notes, same API shape as OpenAI. |

## AI stand-up host

| Variable | Default | Purpose |
|---|---|---|
| `MIA_MODE` | `realtime` | `realtime` (speech-to-speech) or `pipeline`. |
| `MIA_MODEL_PROVIDER` | - | Picks the stand-up voice from `.env` instead of the app. Realtime: `google`, `openai`, `xai`. Pipeline: `openai`, `anthropic`. Without it (and without a pick in the app) stand-ups can't be booked. |
| `MIA_MODEL` | - | Model name; required for OpenAI. |
| `MIA_VOICE` | - | With `MIA_MODEL_PROVIDER`: realtime voice (Google: Puck, Charon, Kore, …) or pipeline voice id. |
| `MIA_VOICE_PROVIDER` | `openai` | Pipeline only: `openai` or `elevenlabs`. |
| `MIA_TRANSCRIBER_PROVIDER` / `MIA_TRANSCRIBER_MODEL` | `deepgram` / `nova-3` | Pipeline only. |
| `STANDUP_SILENCE_LEAVE_SECONDS` | `180` | Safety net without `PUBLIC_URL`: the stand-up bot leaves after this much participant silence (it normally leaves 60 s after everyone else does). Keep it long; the agent's own speech doesn't count. |

Providers other than Gemini Live need their API key added to your MeetStream account first.

## Report delivery

| Variable | Purpose |
|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | Email delivery. |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook for meeting summaries. |

Turn delivery on in Admin → Bot & settings.

## Task tools

| Tool | Variables |
|---|---|
| ClickUp | `CLICKUP_API_TOKEN`, `CLICKUP_LIST_ID` |
| Jira Cloud | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `JIRA_ISSUE_TYPE` |
| Asana | `ASANA_ACCESS_TOKEN`, `ASANA_PROJECT_GID` |
| Trello | `TRELLO_API_KEY`, `TRELLO_TOKEN`, `TRELLO_LIST_ID`, `TRELLO_DONE_LIST_ID` |
| monday.com | `MONDAY_API_TOKEN`, `MONDAY_BOARD_ID`, `MONDAY_STATUS_COLUMN_ID` |

`INTEGRATION_SYNC_MINUTES` (default 15) sets how often task status is read back.
