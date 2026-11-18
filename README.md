# Employee Progress Tracker

An AI meeting notetaker that also keeps a running record of **what every person is working on**: a
[MeetStream](https://meetstream.ai) bot joins your meetings, asks for recording consent, and writes
the notes, like Read AI or Fireflies do. On top of that, each person's commitments, completed work,
pending items and blockers are carried from one meeting to the next. Managers get a team view.
Employees get their own history and can correct what the AI recorded.

It is a self-hosted example app: clone it, add two API keys, run it. There is no hosted service.

![stack](https://img.shields.io/badge/backend-FastAPI%20%2B%20SQLite-166554) ![stack](https://img.shields.io/badge/frontend-React%20%2B%20Vite-166554) ![stack](https://img.shields.io/badge/AI-Claude%20or%20Gemini%20%2B%20MeetStream%20MIA-166554)

---

## What it does

| Area | What you get |
|---|---|
| **AI notetaker** | Send the bot to any Zoom, Google Meet or Teams link (now, or at a set time). Once admitted, it introduces itself as an AI notetaker in the chat, says the meeting is recorded and transcribed, and explains how to opt out. After the call: summary, key points, decisions, action items with owners and deadlines, open questions, and a per-person update. The report can be downloaded as Markdown. |
| **Scheduling** | Recurring schedules (once, daily, weekdays, weekly on chosen days), any number per day, in any timezone. The bot joins on its own. Manual "send bot now" is always available. |
| **Calendar auto-join** | Connect Google Calendar or Outlook (through MeetStream) and the bot joins calendar meetings on its own, with include/exclude title filters, or you send it to individual events from the list. |
| **Progress tracking** | Each meeting produces *updates* (what someone said) that move long-lived *work items* (planned → in progress → blocked → done). Items not reported as finished are **carried forward**. Blockers are tracked until resolved. Every change keeps a history with the meeting it came from. |
| **AI stand-up mode** | Instead of only listening, the bot **runs the stand-up by voice**. It goes person by person through what they finished, today's plan, what's left and blockers. It asks follow-ups, and it is briefed with each person's unfinished commitments so it can ask "you planned to finish X - did that happen?" |
| **Dashboards** | Manager: a "needs your attention" list first (overdue work, open blockers, work that keeps slipping), then team overview, latest update per person, overdue and carried-over work, blockers, project progress, 14-day trend, upcoming meetings. Employee: personal work items, update timeline, blockers, meeting history, plus **confirm / correct** for each AI-recorded update and item. |
| **Work board** | Every open commitment as a board (planned / in progress / blocked / done), filtered by person or project. Drag a card to change its status; the move is logged in the item's history. |
| **Ask & search** | Ask questions across all meetings ("what is blocking the team?", "what did Priya commit to?") and get answers with the meeting and date cited, built only from records you may see. Ctrl+K opens a command menu to jump to any page, person, meeting or work item. |
| **Reports** | Daily, weekly and monthly reports by team, project or person, viewable in the app and exportable as Markdown. After each meeting the report can be emailed to everyone it's shared with (each gets their own filtered version) and summarised in Slack. |
| **Report sharing** | Per meeting, the organizer chooses who sees the **full report** and, separately, who sees **individual employee updates**: only the organizer, all participants, managers and team leads, or specific people. Everyone always sees their own update. |
| **Task tools** | Optional ClickUp, Jira, Asana, Trello and monday.com integrations: push a work item as a task (or auto-push new action items), and sync status back so finishing a Jira issue marks the item done. |
| **People and teams** | Employee profiles with aliases ("Sam O", "samo-laptop"), teams with leads, and projects with keywords. Meeting display names are matched to people automatically; fixing a match teaches the alias for next time. |
| **Privacy and consent** | Notice on admission, separate notice for late joiners, per-person opt-out (their speech is removed before analysis), pause/resume recording, remove bot, a consent audit log per meeting, role-based access to transcripts and reports, automatic transcript and recording deletion after N days, "delete recording" per meeting, and "erase all data" per person. |

## Quick start

Needs **Python 3.11+** and **Node 18+**.

```bash
git clone <this repo> employee-progress-tracker
cd employee-progress-tracker
cp .env.example .env          # add MEETSTREAM_API_KEY and ANTHROPIC_API_KEY or GEMINI_API_KEY
```

Backend (terminal 1):

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip install -r requirements.txt
.venv/bin/python scripts/seed_demo.py              # optional: demo team with a week of meetings
.venv/bin/python -m uvicorn app.main:app --port 8000
```

Frontend (terminal 2):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. On a fresh database the first account you create becomes the admin. With
the demo loaded, sign in as `admin@demo.local`, `maya@demo.local` (manager), `priya@demo.local` (team
lead) or `sam@demo.local` (employee). The password for all four is `demo-password`.

### Docker

```bash
cp .env.example .env    # add your keys
docker compose up --build
```

The app (UI and API) is then at http://localhost:8000, with the database on a Docker volume.

For a single-process setup without Docker, run `npm run build` in `frontend/`; the backend then serves the built UI
at http://localhost:8000.

### Keys

| Variable | Needed for | Where |
|---|---|---|
| `MEETSTREAM_API_KEY` | Sending bots, stand-up agents, transcripts | https://app.meetstream.ai/api-key |
| `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` | Analysing transcripts (Claude or Gemini) | https://console.anthropic.com or https://aistudio.google.com/apikey |
| `PUBLIC_URL` *(optional)* | Webhooks and live look-ups by the stand-up agent | `ngrok http 8000` or `cloudflared tunnel --url http://localhost:8000` |

Without `MEETSTREAM_API_KEY` you can still use **Import transcript** (paste `Name: text` lines) to try
the analysis and tracking. Without a public URL the app **polls** MeetStream for bot status, the
participant roster and transcripts, so a laptop install works end to end.

## How it works

```
                 ┌──────────── backend (FastAPI) ─────────────────────────────────┐
 Schedules ────► │ scheduler ──► create_bot (join_at)  ──────────────────────────────────► MeetStream
 "Send bot" ───► │                 + MIA agent for stand-ups                       │       bot in Zoom/Meet/Teams
                 │ watcher (poll)  ◄── status, participants, chat ◄──────────────────────┤
 webhooks ─────► │   • on admission: post consent notice                           │
 (optional)      │   • new names on roster: late-joiner notice                     │
                 │   • "pause recording" in chat: pause_recording                  │
                 │ on end ──► get_transcript ──► speakers → employees              │
                 │           ──► opt-outs redacted ──► Claude (structured output)  │
                 │           ──► updates, work items, blockers, history ──► report │
                 └──────────────────────────────── SQLite ─────────────────────────┘
                                         ▲
                     React UI: dashboards, meetings, schedules, reports, admin
```

**The analysis step** sends Claude the transcript *plus* each attendee's open work items and blockers
(with ids). Claude returns a typed JSON object:
meeting notes, then per person what was completed, in progress, planned and pending, blockers,
commitments with resolved dates, status changes to existing items by id, and genuinely new items. The
tracker applies this deterministically. It de-duplicates similar titles, marks items carried over,
merges repeated blockers, and logs every change. Re-analysing a meeting replaces its updates without
double-counting history. With Claude, the model and effort are set by `ANALYSIS_MODEL` / `ANALYSIS_EFFORT`, and the server-side
refusal fallback is on. With Gemini (`GEMINI_API_KEY`, `GEMINI_MODEL`), the same JSON schema is sent as
`responseJsonSchema` and the reply is validated against it. In testing, `gemini-2.5-pro` resolved dates
correctly where `gemini-2.5-flash` did not. Model output varies between runs, so the tracker also
creates work items from an update's completed / in-progress / planned lists when the model leaves
"new work items" empty, and matches reworded titles to existing items.

## MeetStream features used

Everything below is a documented MeetStream API. Nothing here relies on undocumented behaviour; where
the API has limits, the app says so.

| Need | MeetStream API |
|---|---|
| Join a meeting, now or later | `POST /bots/create_bot` (with `join_at`, `automatic_leave`, `recording_config.transcript`, `retention`, `custom_attributes`, `Idempotency-Key`) |
| Cancel a booked bot | `DELETE /calendar/scheduled_bots/{id}` |
| Status | `GET /bots/{id}/status`, webhooks via `callback_url` (`bot.inmeeting`, `bot.stopped` + `bot_event`, `bot.done`, ...) |
| Consent notice / late joiners | `POST /bots/{id}/send_message`, `GET /bots/{id}/get_participants`, `participant_events.join` via `realtime_endpoints` |
| Privacy window | `POST /bots/{id}/pause_recording` / `resume_recording`, `GET /bots/{id}/remove_bot` |
| Opt-outs | `GET /bots/{id}/get_chats` |
| Transcript | `GET /bots/{id}/detail`, `GET /bots/{id}/transcriptions`, `GET /transcript/{id}/get_transcript` |
| AI stand-up | `POST /mia` (pipeline voice agent with system prompt and MCP server), attached with `agent_config_id`; `DELETE /mia` afterwards |

Lessons taken from the MeetStream [companion](https://github.com/meetstream-ai/companion) and
[labs](https://github.com/meetstream-ai/labs) repos: the intro is sent after admission (a
`bot_message` sent in the waiting room is lost), `video_required: false` is sent explicitly, `202`
means "not ready", `507` is an idempotent replay, terminal reasons come from `bot_event`, deliveries
are de-duplicated, and a stand-up bot gets `agent_config_id` only.

## Consent and privacy: what is and isn't possible

* **Notice:** posted in the meeting chat as soon as the bot is admitted (editable under Admin → Bot &
  settings). In a live Google Meet test it went out about 15 seconds after the host admitted the bot.
* **Late joiners:** MeetStream only exposes the participant list after the call (`get_participants`
  answers 404 while the bot is in the meeting). With `PUBLIC_URL` set, `participant_events.join`
  webhooks arrive live and each late joiner gets a notice by name. Without it, the bot re-posts a
  short reminder every 10 minutes while recording (`consent_reminder_minutes`, 0 turns it off).
* **Stand-up mode** also asks out loud whether everyone is OK with recording before it starts.
* **Opt-out:** a participant types "opt out" (phrases are configurable) in the chat. The chat is read
  after the call; that person's speech is replaced with a placeholder before the transcript reaches
  Claude, and no update is recorded for them.
* **Pause:** the organizer, managers and admins can pause, resume or remove the bot from the meeting
  page. Typing "pause recording" in the chat does **not** work live: MeetStream returns the chat only
  after the call (`get_chats` answers 202 during it). Use the dashboard controls.
* **Transcripts:** silence can come back as filler ("Thank you." every ~30 seconds). Short phrases
  that repeat three or more times are dropped before analysis.
* **Platform limits apply:** hosts can deny the bot (recorded as *Denied*, never retried), waiting
  rooms need someone to admit it, and Zoom may ask the host for recording permission
  (`recording_permission_denied_timeout` is set). The bot cannot hear a verbal objection in notetaker
  mode: there is no live transcript, so it cannot act on one.
* **Access:** admins see everything. Managers see all employee records. Team leads see their team.
  Employees see their own records. Meeting reports follow the organizer's sharing choice. Transcripts
  are part of the full report.

## AI stand-up mode

Pick **AI stand-up** when sending a bot or creating a schedule. Before joining, the app creates a
MeetStream MIA agent. Its prompt holds the roster (the meeting's team, or everyone; up to 15 people)
and, for each person, their open work, deadlines, how often items were carried over, blockers and
last update. The agent runs the round person by person, asks one follow-up when an answer is vague,
and finishes with a recap. The call is transcribed as usual and goes through the same analysis. The
agent is deleted when the meeting ends.

The voice stack is set by `MIA_*` variables (default: OpenAI `gpt-4.1` with Deepgram `nova-3`
transcription in pipeline mode). MeetStream rejects the agent (HTTP 400, "provider API key not
configured") unless those providers' keys are added in the MeetStream dashboard; the error appears on
the meeting. With
`PUBLIC_URL` set, the agent can also call this app's `/mcp` endpoint (`get_person_context`,
`list_standup_roster`) to look up someone who wasn't on the roster.

## Calendar auto-join

Connect a calendar under **Schedules → Calendar auto-join** (admin only) with an OAuth client ID,
secret and refresh token for Google (Calendar API) or Microsoft (Graph, `Calendars.Read`). The
credentials are passed to MeetStream, which keeps the calendar in sync; this app does not store them.
MeetStream's [labs](https://github.com/meetstream-ai/labs) repo has helpers that produce the refresh
token (`google-calendar-integration`, `outlook-calendar-integration`).

With auto-join on, the app reads upcoming events every two minutes and books the bot for each
meeting that has a link and passes the title filters, through the same path as scheduled meetings,
so consent notices, analysis and progress tracking all apply.

## Report delivery

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` for email and/or
`SLACK_WEBHOOK_URL` (a Slack incoming webhook), then turn delivery on under Admin → Bot & settings.
Each person allowed to see the full report gets it by email, with individual updates filtered by the
employee-update sharing setting. Slack gets a short summary and a link, and only for reports shared
with participants or managers. A report is sent once; "Send report" on the meeting page resends it.

## Task-tool integrations

Set the variables for any tool in `.env` (see `.env.example`) and restart. Work items then get a
"Create in …" button, and **Admin → Bot & settings → Create tasks automatically** can push every new
action item. Status sync runs every `INTEGRATION_SYNC_MINUTES` minutes, or on demand:

| Tool | Creates | Reads back |
|---|---|---|
| ClickUp | task in `CLICKUP_LIST_ID` | status type (done/closed) |
| Jira Cloud | issue in `JIRA_PROJECT_KEY` | status category (new / in progress / done) |
| Asana | task in `ASANA_PROJECT_GID` | `completed` |
| Trello | card in `TRELLO_LIST_ID` | `dueComplete`, or moved to `TRELLO_DONE_LIST_ID` |
| monday.com | item on `MONDAY_BOARD_ID` | text of `MONDAY_STATUS_COLUMN_ID` |

## Project layout

```
backend/
  app/main.py                 FastAPI app, background workers, serves the built UI
  app/models.py               tables: people, schedules, meetings, updates, work items, blockers, consent log
  app/access.py               who may see what
  app/api/                    routes: auth, org (teams/projects/people/users/settings), meetings, progress, webhooks, mcp
  app/services/meetstream.py  MeetStream REST client
  app/services/bots.py        create_bot payload, pause/resume/remove, MIA lifecycle
  app/services/workers.py     scheduler + polling watcher (+ status transitions shared with webhooks)
  app/services/consent.py     notices, late joiners, chat opt-outs, pause commands
  app/services/processing.py  post-call pipeline
  app/services/extraction.py  Claude structured analysis
  app/services/tracker.py     applies the analysis: updates, items, carry-over, blockers
  app/services/standup.py     MIA stand-up agent prompt and config
  app/services/reports.py     meeting report and period reports
  app/services/integrations/  ClickUp, Jira, Asana, Trello, monday.com
  scripts/seed_demo.py        demo data (no keys needed)
  tests/                      pytest, MeetStream and Claude mocked
frontend/src/
  pages/                      Dashboard, MyProgress, Board, Ask, Meetings, MeetingDetail, Schedules,
                              People, EmployeeProfile, Projects, Reports, Admin
  components/                 UI kit, app shell (mobile drawer), command menu, calendar panel,
                              work-item editor with history, update review card, sharing picker
  api.js                      every HTTP call
```

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q
cd frontend && npm test
```

CI (`.github/workflows/ci.yml`) runs both suites, the frontend build and the Docker build on every push.

The tests cover recurrence and timezones, transcript shapes, name matching, carry-over, de-duplication, opt-out redaction, the full post-call pipeline, the consent notice and
late-joiner flow, webhook de-duplication and stop reasons, access rules for each role, employee
corrections, the MCP token check, calendar auto-join, report delivery and its sharing rules, search and
ask privacy, retention and erasure, and that the migrations match the models.

## Notes and limits

* The schedule runs inside the backend process: keep it running for bots to be booked. Each
  occurrence is booked with MeetStream's `join_at` about 10 minutes ahead.
* The schema is managed with Alembic (`backend/app/migrations`) and upgraded on startup. After
  changing a model run `alembic revision --autogenerate -m "..."` in `backend/`; a test fails if a
  model change has no migration. Databases created before migrations existed are upgraded in place.
* SQLite is the default. Set `DATABASE_URL` for Postgres (install a driver such as `psycopg`).
* Speaker attribution follows MeetStream's per-participant transcript. If a room shares one device,
  map the name by hand on the meeting page.
* AI output can be wrong. That is why every update and item can be confirmed or corrected by the
  person it is about, with the change kept in history.

## License

MIT
