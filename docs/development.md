# Development

## Run from source

Needs Python 3.11+ and Node 18+.

```bash
cp .env.example .env
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt            # Windows: .venv\Scripts\pip ...
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev                                          # http://localhost:5173, proxies /api to :8000
```

`npm run build` puts the UI in `frontend/dist`, which the backend then serves itself on port 8000.

## Demo data

To explore the UI without any keys, load a demo team with a week of meetings:

```bash
cd backend
.venv/bin/python scripts/seed_demo.py           # refuses if the database already has users
.venv/bin/python scripts/seed_demo.py --reset   # wipes the database first
```

The script prints the demo logins. The demo meetings go through the real tracker code with
hand-written analysis, so no AI or MeetStream calls are made.

**Import transcript** on the Meetings page analyses a pasted `Name: text` transcript without a bot,
which is the quickest way to try the analysis.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q     # API, pipeline, access rules, migrations
cd frontend && npm test                         # Vitest
```

The backend suite is hermetic: a throwaway SQLite database, MeetStream and the AI providers mocked.
CI (`.github/workflows/ci.yml`) runs both suites, the frontend build and the Docker build.

## Database migrations

The schema is managed with Alembic (`backend/app/migrations`) and upgraded automatically on startup.
After changing `backend/app/models.py`:

```bash
cd backend
.venv/bin/python -m alembic revision --autogenerate -m "describe the change"
```

Review the generated file. `tests/test_migrations.py` fails when a model change has no migration.

## Project layout

```
backend/
  app/main.py                FastAPI app, background workers, serves the built UI
  app/models.py              people, schedules, meetings, updates, work items, blockers, consent log
  app/access.py              who may see what
  app/api/                   routes: auth, org, meetings, progress, calendar, knowledge, agent, webhooks, mcp
  app/services/              meetstream client, bots, workers, consent, processing, extraction (Claude/Gemini),
                             tracker, standup, reports, delivery, knowledge (search/ask), retention, integrations
  app/migrations/            Alembic
  scripts/seed_demo.py       demo data
  tests/
frontend/src/
  pages/                     Dashboard, MyProgress, Board, Ask, Meetings, MeetingDetail, Schedules,
                             People, EmployeeProfile, Projects, Reports, Admin
  components/                UI kit, app shell, command menu, calendar panel, work-item editor, review card
  api.js                     every HTTP call
assets/branding/             logo files
docs/                        this documentation
```

## Conventions

- Every data-changing route checks a role or ownership; every read goes through `app/access.py`.
- Timestamps leave the API with an explicit UTC offset (`serializers.iso`).
- Errors say what to do next, never a raw exception string.
- Frontend calls go through `frontend/src/api.js`.
