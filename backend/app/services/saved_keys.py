"""Keys and connection settings entered in the setup wizard.

Self-hosters can type their keys into the browser instead of editing .env.
They are stored in the app_settings table (as "key:<FIELD>") and applied to
the running `settings` object at startup and whenever they are saved. A value
set in the environment (.env) always wins and is never overwritten.

They are kept in the database in plain text, like .env keeps them on disk:
protect the database file (or volume) the same way.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppSetting

#: What the wizard may set, and whether the value is secret (never sent back).
FIELDS: Dict[str, bool] = {
    "MEETSTREAM_API_KEY": True,
    "ANALYSIS_PROVIDER": False,
    "GEMINI_API_KEY": True,
    "ANTHROPIC_API_KEY": True,
    "SLACK_WEBHOOK_URL": True,
    "SMTP_HOST": False,
    "SMTP_PORT": False,
    "SMTP_USER": False,
    "SMTP_PASSWORD": True,
    "SMTP_FROM": False,
    "GOOGLE_CLIENT_ID": False,
    "GOOGLE_CLIENT_SECRET": True,
}
PREFIX = "key:"
_from_env: Dict[str, bool] = {}


def _env_set(field: str) -> bool:
    if field not in _from_env:
        # Captured once, before any saved value is applied to `settings`.
        _from_env[field] = bool(os.environ.get(field)) or _in_dotenv(field)
    return _from_env[field]


def _in_dotenv(field: str) -> bool:
    value = getattr(settings, field, None)
    return value not in (None, "") and not _applied.get(field)


_applied: Dict[str, bool] = {}


def _coerce(field: str, value: Any) -> Any:
    if field == "SMTP_PORT":
        return int(value)
    return value


def apply(db: Session) -> None:
    """Load saved values into `settings` for every field the environment left empty."""
    for field in FIELDS:
        _env_set(field)
    for row in db.query(AppSetting).filter(AppSetting.key.like(PREFIX + "%")):
        field = row.key[len(PREFIX):]
        if field in FIELDS and not _from_env.get(field) and row.value not in (None, ""):
            setattr(settings, field, _coerce(field, row.value))
            _applied[field] = True


def save(db: Session, values: Dict[str, Any]) -> None:
    """Save (or with "" clear) values. Fields set in the environment are skipped."""
    for field, value in values.items():
        if field not in FIELDS or _env_set(field):
            continue
        value = value.strip() if isinstance(value, str) else value
        row = db.get(AppSetting, PREFIX + field)
        if value in (None, ""):
            if row is not None:
                db.delete(row)
            if _applied.pop(field, None):
                setattr(settings, field, type(settings).model_fields[field].default)
            continue
        if field == "SMTP_PORT":
            value = int(value)
        if row is None:
            db.add(AppSetting(key=PREFIX + field, value=value))
        else:
            row.value = value
        setattr(settings, field, _coerce(field, value))
        _applied[field] = True
    db.commit()


def describe() -> Dict[str, Dict[str, Any]]:
    """For the wizard: which fields are set, and where from. Secrets are not returned."""
    out = {}
    for field, secret in FIELDS.items():
        value = getattr(settings, field, None)
        is_set = value not in (None, "")
        out[field] = {"set": is_set, "from_env": _env_set(field),
                      "value": None if secret or not is_set else value}
    return out
