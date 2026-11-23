# Contributing to MeetPact

Thanks for helping. Bug reports, fixes, docs and features are all welcome.

## Before you start

- For anything bigger than a small fix, open an issue first so we can agree on the approach.
- Security problems: please follow [SECURITY.md](SECURITY.md) instead of opening an issue.

## Set up

See [docs/development.md](docs/development.md). In short:

```bash
cp .env.example .env
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
cd ../frontend && npm install
```

`backend/scripts/seed_demo.py` loads demo data so you can work on the UI without any API keys.

## Making a change

1. Branch from `main`.
2. Keep the change focused; one topic per pull request.
3. Add or update tests. The backend suite is hermetic - mock MeetStream and the AI providers rather
   than calling them (see `backend/tests/conftest.py`).
4. If you change `backend/app/models.py`, add an Alembic migration
   (`alembic revision --autogenerate -m "..."` in `backend/`).
5. Run everything CI runs:

   ```bash
   cd backend && .venv/bin/python -m pytest -q
   cd frontend && npm test && npm run build
   ```

6. Open a pull request using the template. Describe what changed, why, and how you tested it.

## Guidelines

- Access control lives in `backend/app/access.py`. Every new read must go through it; every new
  write needs a role or ownership check.
- Never log or return API keys, tokens or passwords.
- Errors shown to users should say what to do next.
- Use only documented MeetStream APIs, and keep consent and privacy behaviour honest in the docs.
- UI: reuse the components in `frontend/src/components/ui.jsx` and keep the neubrutalist style.

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
