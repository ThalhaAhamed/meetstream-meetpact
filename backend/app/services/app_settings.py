"""Settings an admin can change from the UI (stored in the app_settings table)."""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppSetting

DEFAULTS: Dict[str, Any] = {
    "bot_name": settings.BOT_NAME,
    # Posted once in the meeting chat when the bot is admitted. Empty turns it off.
    "consent_notice": (
        "Hi everyone, I'm {bot_name}, an AI notetaker added by {organizer}. "
        "This meeting is being recorded and transcribed for meeting notes."
    ),
    # Default report sharing for meetings created without a schedule.
    "default_share_full": {"audience": "participants", "user_ids": []},
    "default_share_employee": {"audience": "managers", "user_ids": []},
    # Create task-tool tasks automatically for new AI action items.
    "auto_push_provider": None,
    # Bearer token for the stand-up agent's MCP calls (generated on first use).
    "mcp_token": None,
    # Calendar auto-join (calendar connected through MeetStream).
    "calendar_connected": False,
    "calendar_account": None,
    "calendar_owner_user_id": None,
    "calendar_auto_join": False,
    "calendar_include_keywords": [],
    "calendar_exclude_keywords": ["1:1", "personal", "lunch"],
    # Report delivery after each meeting (to the people it is shared with).
    "deliver_email": False,
    "deliver_slack": False,
    # Data retention: transcripts older than this many days are deleted (0 = keep).
    "transcript_retention_days": 0,
}

# Never returned by the settings API.
SECRET_KEYS = {"mcp_token"}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    return row.value if row is not None else DEFAULTS.get(key)


def all_settings(db: Session) -> Dict[str, Any]:
    out = dict(DEFAULTS)
    for row in db.query(AppSetting).all():
        if row.key in DEFAULTS:  # ignore settings from older versions
            out[row.key] = row.value
    return out


def set_settings(db: Session, values: Dict[str, Any]) -> None:
    for key, value in values.items():
        if key not in DEFAULTS:
            continue
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    db.commit()
