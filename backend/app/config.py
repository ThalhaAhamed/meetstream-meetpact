"""Application settings, read from environment variables (or a .env file).

Every setting has a working default so the app boots with no configuration;
only MEETSTREAM_API_KEY (to send bots) and ANTHROPIC_API_KEY (to analyse
transcripts) are needed for the real meeting flow.
"""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Server ---------------------------------------------------------
    DATABASE_URL: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'tracker.db').as_posix()}"
    SECRET_KEY: str = ""  # signs session cookies; generated and stored in data/ when empty
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    # Public HTTPS base URL that forwards to this server (ngrok / cloudflared).
    # Optional. With it MeetStream can push webhooks (lifecycle, participant
    # joins) and the stand-up agent can call back into the MCP endpoint.
    # Without it everything still works through polling.
    PUBLIC_URL: Optional[str] = None
    TIMEZONE: str = "UTC"  # default timezone for schedules
    # Without PUBLIC_URL, start a Cloudflare quick tunnel automatically if
    # cloudflared is installed ("auto"), or never ("off").
    TUNNEL: str = "auto"
    CLOUDFLARED_PATH: Optional[str] = None
    PORT: int = 8000  # the port the backend listens on (the tunnel points here)
    BACKGROUND_WORKERS: bool = True  # scheduler + bot watcher loops

    # ---- MeetStream -----------------------------------------------------
    MEETSTREAM_API_KEY: Optional[str] = None
    MEETSTREAM_BASE_URL: str = "https://api.meetstream.ai/api/v1"
    MEETSTREAM_WEBHOOK_SECRET: Optional[str] = None  # workspace webhook signing secret, optional
    BOT_NAME: str = "MeetPact AI Notetaker"
    # Post-call transcription provider. "meetstream" needs no extra key on the
    # MeetStream account; "deepgram" / "assemblyai" need that provider set up there.
    TRANSCRIPT_PROVIDER: str = "meetstream"
    TRANSCRIPT_LANGUAGE: str = "en"  # "auto" lets the meetstream provider detect it
    RETENTION_HOURS: int = 168
    WAITING_ROOM_TIMEOUT: int = 600
    EVERYONE_LEFT_TIMEOUT: int = 120
    IN_CALL_RECORDING_TIMEOUT: int = 14400  # API minimum is 600
    SCHEDULE_LEAD_MINUTES: int = 10  # create join_at bots this long before start
    # Without PUBLIC_URL (no leave tool) a stand-up bot leaves 60 s after everyone
    # else has left; this silence timeout is only a safety net. MeetStream counts
    # silence from the participants only - the agent's own speech does not reset
    # it - so a short value ends the meeting while the agent is still talking
    # (seen live: a 60 s value removed the bot 69 s into the stand-up).
    STANDUP_SILENCE_LEAVE_SECONDS: int = 180

    # ---- Stand-up agent (MeetStream MIA) ---------------------------------
    # Default: Gemini Live (speech-to-speech), which a MeetStream account can use
    # without adding its own provider key. Pipeline mode chains a transcriber,
    # an LLM and a voice; its providers' keys must be added in MeetStream first
    # (e.g. MIA_MODE=pipeline, MIA_MODEL_PROVIDER=anthropic, MIA_VOICE_PROVIDER=elevenlabs).
    MIA_MODE: str = "realtime"
    MIA_MODEL_PROVIDER: str = "google"
    MIA_MODEL: str = ""  # required for openai only
    MIA_VOICE_PROVIDER: str = "openai"  # pipeline mode only
    MIA_VOICE: str = "Puck"  # realtime: Google Puck/Charon/Kore/...; pipeline: the provider's voice id
    MIA_TRANSCRIBER_PROVIDER: str = "deepgram"
    MIA_TRANSCRIBER_MODEL: str = "nova-3"

    # ---- AI analysis (Claude or Gemini) ----------------------------------
    # "anthropic" | "gemini"; empty = whichever key is set (Claude if both).
    ANALYSIS_PROVIDER: str = ""
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-pro"  # most accurate in testing; gemini-3.8-flash is faster
    ANTHROPIC_API_KEY: Optional[str] = None
    ANALYSIS_MODEL: str = "claude-opus-5-5"
    ANALYSIS_EFFORT: str = "high"

    # ---- Task-tool integrations (all optional) ---------------------------
    CLICKUP_API_TOKEN: Optional[str] = None
    CLICKUP_LIST_ID: Optional[str] = None
    JIRA_BASE_URL: Optional[str] = None  # https://your-site.atlassian.net
    JIRA_EMAIL: Optional[str] = None
    JIRA_API_TOKEN: Optional[str] = None
    JIRA_PROJECT_KEY: Optional[str] = None
    JIRA_ISSUE_TYPE: str = "Task"
    ASANA_ACCESS_TOKEN: Optional[str] = None
    ASANA_PROJECT_GID: Optional[str] = None
    TRELLO_API_KEY: Optional[str] = None
    TRELLO_TOKEN: Optional[str] = None
    TRELLO_LIST_ID: Optional[str] = None
    TRELLO_DONE_LIST_ID: Optional[str] = None
    MONDAY_API_TOKEN: Optional[str] = None
    MONDAY_BOARD_ID: Optional[str] = None
    MONDAY_STATUS_COLUMN_ID: str = "status"
    INTEGRATION_SYNC_MINUTES: int = 15

    # ---- Google Calendar sign-in (optional) -------------------------------
    # An OAuth "Web application" client from Google Cloud. With these set,
    # Schedules -> Calendar auto-join shows "Connect Google Calendar", which
    # signs in with Google and hands the refresh token to MeetStream.
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    # Must match an "Authorized redirect URI" on the client exactly.
    # Default: http://localhost:<PORT>/api/calendar/google/callback
    GOOGLE_REDIRECT_URI: Optional[str] = None

    # ---- Report delivery (optional) ---------------------------------------
    # The address people open MeetPact at. On a server set it to your domain
    # (https://meetpact.example.com): report links, Google sign-in and
    # MeetStream's callbacks all follow from it. On localhost, links are left
    # out of Slack/email and the automatic tunnel serves MeetStream instead.
    APP_URL: str = "http://localhost:5173"
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: Optional[str] = None
    SMTP_STARTTLS: bool = True
    SLACK_WEBHOOK_URL: Optional[str] = None  # Slack incoming webhook for meeting summaries

    @property
    def app_url_is_public(self) -> bool:
        """True when APP_URL is a real address others can reach (a server,
        not this laptop). Then it doubles as the public URL for MeetStream,
        report links are included, and no tunnel is needed."""
        from urllib.parse import urlparse

        host = (urlparse(self.APP_URL).hostname or "").lower()
        local = host in ("", "localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith((".local", ".localhost"))
        return not local

    @property
    def public_url(self) -> Optional[str]:
        """Where MeetStream can reach this server: PUBLIC_URL if set, else APP_URL
        when it is a public address, else the automatic tunnel while it is up."""
        if self.PUBLIC_URL:
            return self.PUBLIC_URL.rstrip("/")
        if self.app_url_is_public:
            return self.APP_URL.rstrip("/")
        from app.services.tunnel import tunnel

        return tunnel.url if tunnel.state == "up" else None


settings = Settings()


def secret_key() -> str:
    """The cookie-signing key: from env, else a random one persisted in data/."""
    if settings.SECRET_KEY:
        return settings.SECRET_KEY
    path = BACKEND_DIR / "data" / ".secret_key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()
