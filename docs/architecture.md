# Architecture

## The pipeline

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

## MeetStream APIs used

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

## Known limits

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
