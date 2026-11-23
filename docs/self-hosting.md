# Self-hosting

MeetPact is a single container with a SQLite file (or Postgres). Run it on any machine with Docker
and an address your team and MeetStream can reach. There is no hosted MeetPact: each team runs its own.

## What you need

* A server or container host with Docker, and a domain or subdomain pointing at it
  (e.g. `meetpact.example.com`).
* HTTPS in front of it. The Caddy example below does this automatically.
* A MeetStream API key and an analysis key (Gemini or Claude). See [configuration](configuration.md).

## The one setting that matters: `APP_URL`

Set `APP_URL` to the address people open MeetPact at, e.g. `APP_URL=https://meetpact.example.com`.
Everything that needs a public address follows from it:

| Uses `APP_URL` | |
|---|---|
| Report links in Slack and email | "Open the full report" points at your server |
| MeetStream callbacks | lifecycle and participant webhooks, the stand-up host's *leave* and *who is here* tools, MCP |
| Google Calendar sign-in | redirect URI `https://<your domain>/api/calendar/google/callback` |
| Session cookie | marked `Secure` when `APP_URL` is `https://` |

No tunnel is started when `APP_URL` is public. On `localhost` (a laptop), report links are left out
of Slack and email because nobody else could open them, and MeetPact opens a Cloudflare tunnel for
MeetStream if `cloudflared` is installed. `PUBLIC_URL` still overrides the address used for
MeetStream if it must differ from `APP_URL`.

## Docker Compose on a server

```bash
git clone https://github.com/<you>/meetpact.git && cd meetpact
cp .env.example .env
# edit .env: APP_URL=https://meetpact.example.com, SECRET_KEY=<long random string>,
#            MEETSTREAM_API_KEY, GEMINI_API_KEY (or ANTHROPIC_API_KEY), optional integrations
docker compose up -d --build
```

The app listens on port 8000; data lives in the `tracker-data` volume. Put HTTPS in front with
[Caddy](https://caddyserver.com/) (gets and renews a certificate by itself):

```
# /etc/caddy/Caddyfile
meetpact.example.com {
    reverse_proxy localhost:8000
}
```

Then open `https://meetpact.example.com`. The first visit asks you to create the admin account; there
is no public sign-up. The admin adds everyone else under **Admin → Users** and **People**.

Generate `SECRET_KEY` once, for example with `openssl rand -hex 32`, and keep it: changing it signs
everyone out.

## Container platforms

Any host that runs a Dockerfile works (Render, Railway, Fly.io, a Kubernetes cluster):

* Build from the repository's `Dockerfile`. It listens on `$PORT` when the platform sets one, else 8000.
* Attach a persistent disk at `/data` (SQLite), or set `DATABASE_URL` to Postgres.
* Set the environment variables from `.env.example` in the platform's settings, with `APP_URL` = the
  URL the platform gives you or your custom domain.
* Health check: `GET /api/health`.

## After it is running

1. **Admin → Server setup** shows the public address MeetStream will use.
2. **Admin → Bot and reports:** *Send test email* / *Send test to Slack*.
3. **Admin → Task tools → Check** for each task tool you set up.
4. **Schedules → Calendar auto-join:** register the redirect URI above on your Google OAuth client,
   then *Connect Google Calendar*.

## Updating and backups

```bash
git pull && docker compose up -d --build   # database migrations run on start
```

Back up the `tracker-data` volume (it holds `tracker.db`), or your Postgres database.
