# Working in this repository

Guidance for AI coding agents (and humans in a hurry). [docs/architecture.md](docs/architecture.md)
explains why things are shaped this way; this file is the how.

## What it is

MeetPact sends a MeetStream bot into a call, analyses the transcript with Claude or Gemini, and
tracks each person's work items, commitments and blockers across meetings. In stand-up mode a
MeetStream MIA voice agent runs the meeting.

## Map

```
backend/app/api/        FastAPI routers (auth, org, meetings, progress, calendar, knowledge, agent, webhooks, mcp)
backend/app/services/   logic: processing.py is the post-call pipeline; tracker.py applies analyses
backend/app/access.py   who may see what - every read goes through it
backend/app/models.py   SQLAlchemy models; backend/app/migrations is Alembic
frontend/src/           React + Vite + Tailwind; pages/, components/, api.js (all HTTP calls)
docs/                   user and developer docs
```

## Run, test, verify

```bash
cd backend && .venv/bin/python -m pytest -q
cd frontend && npm test && npm run build
```

A change is done when both pass and, for UI changes, it has been looked at in the browser.

## Rules that are easy to miss

1. **Access:** new reads use `app/access.py`; new writes check role or ownership.
2. **Migrations:** a model change needs an Alembic revision; `tests/test_migrations.py` enforces it.
3. **MeetStream:** only documented endpoints. `video_required: false` is always sent; 202 means not
   ready; terminal reasons come from `bot_event`; the participant list and chat are only available
   after the call.
4. **AI output is untrusted:** the tracker de-duplicates and validates; never let model output pick
   ids that weren't given to it.
5. **Secrets** never leave the server and are never logged.
6. **Tests** mock MeetStream (`monkeypatch` on `MeetStreamClient`) and the AI providers
   (`app.services.processing.analyse_meeting`, `app.services.knowledge.complete_text`).
