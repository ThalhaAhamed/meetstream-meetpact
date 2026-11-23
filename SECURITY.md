# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for security problems. Report them privately through
[GitHub's private vulnerability reporting](https://github.com/meetstream-ai/meetpact/security/advisories/new).
Include a description, steps to reproduce, and the version or commit you tested. You'll get an
acknowledgement within a few days, and fixes are released as soon as they're ready.

## Scope

- The API server (`backend/`), the web UI (`frontend/`), the stand-up agent endpoints
  (`/api/agent/*`, `/mcp`) and the MeetStream webhook receiver (`/api/webhooks/*`).
- Default configuration from `.env.example` and the Docker image.

MeetStream, Anthropic, Google and the task-tool APIs are out of scope; report issues with those to
their vendors.

## Deployment model

MeetPact is meant to be self-hosted by one organisation.

- **Admins** see everything and manage users, settings, calendar and retention. The first account
  created on a fresh install is an admin.
- **Managers** see all employee records; meeting reports follow each meeting's sharing setting.
- **Team leads** see their team's records. **Employees** see their own records and what is shared
  with them.
- Meeting transcripts are part of the full report and follow its sharing setting.
- `/mcp` and `/api/agent/leave` are called by the MeetStream voice agent and require the generated
  bearer token; they are only reachable from outside when `PUBLIC_URL` is set.
- Webhooks: deliveries with a valid `X-MeetStream-Signature` are verified when
  `MEETSTREAM_WEBHOOK_SECRET` is set; unsigned per-bot deliveries are only accepted for bots this
  install launched.
- Calendar OAuth credentials are passed to MeetStream and not stored by MeetPact. API keys live in
  `.env` and are never returned by the API.

## Hardening checklist

- Serve over HTTPS when exposing the app beyond localhost, and set a strong `SECRET_KEY`.
- Keep `.env` out of version control (it is in `.gitignore`).
- Set `transcript_retention_days` in Admin if transcripts shouldn't be kept indefinitely.
