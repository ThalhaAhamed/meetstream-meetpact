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
| `SECRET_KEY` | generated | Signs session cookies. Generated and stored in `backend/data/` when empty. |
| `PUBLIC_URL` | - | Public HTTPS address of the backend. Enables webhooks and the stand-up host's tools. |
| `APP_URL` | `http://localhost:5173` | Base for links in emails and Slack (`http://localhost:8000` with Docker). |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS origin for the dev UI. |
| `TIMEZONE` | `UTC` | Default timezone for new schedules (IANA name). |
| `BACKGROUND_WORKERS` | `true` | Scheduler, bot watcher, calendar sync and housekeeping loops. |

## Bots

| Variable | Default | Purpose |
|---|---|---|
| `BOT_NAME` | `MeetPact AI Notetaker` | Name shown in the meeting (also editable in Admin). |
| `TRANSCRIPT_PROVIDER` | `meetstream` | Post-call transcription: `meetstream`, `deepgram` or `assemblyai`. Some need the provider key added on MeetStream. |
| `TRANSCRIPT_LANGUAGE` | `en` | `auto` lets the `meetstream` provider detect it. |
| `RETENTION_HOURS` | `168` | How long MeetStream keeps the recording. |
| `WAITING_ROOM_TIMEOUT` | `600` | Seconds to wait to be admitted. |
| `EVERYONE_LEFT_TIMEOUT` | `120` | Seconds to stay after everyone else leaves. |
| `IN_CALL_RECORDING_TIMEOUT` | `14400` | Maximum recording length (MeetStream minimum: 600). |
| `SCHEDULE_LEAD_MINUTES` | `10` | How far ahead scheduled meetings are booked with MeetStream (`join_at`). |
| `MEETSTREAM_WEBHOOK_SECRET` | - | Verifies signed workspace webhooks. |

## AI analysis

| Variable | Default | Purpose |
|---|---|---|
| `ANALYSIS_PROVIDER` | auto | `anthropic` or `gemini`. Empty: whichever key is set (Claude if both). |
| `ANALYSIS_MODEL` | `claude-opus-5-5` | Claude model. |
| `ANALYSIS_EFFORT` | `high` | Claude effort level. |
| `GEMINI_MODEL` | `gemini-2.5-pro` | Gemini model. `gemini-3.8-flash` is faster. |

## AI stand-up host

| Variable | Default | Purpose |
|---|---|---|
| `MIA_MODE` | `realtime` | `realtime` (speech-to-speech) or `pipeline`. |
| `MIA_MODEL_PROVIDER` | `google` | Realtime: `google`, `openai`, `xai`. Pipeline: `openai`, `anthropic`. |
| `MIA_MODEL` | - | Model name; required for OpenAI. |
| `MIA_VOICE` | `Puck` | Realtime voice (Google: Puck, Charon, Kore, …) or pipeline voice id. |
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
