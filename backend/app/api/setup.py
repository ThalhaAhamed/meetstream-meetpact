"""The setup wizard: what is configured, saving keys, and live checks."""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import settings
from app.db import get_db
from app.models import Employee, Team, User
from app.services import saved_keys, trello_board, voices
from app.services.app_settings import get_setting, set_settings
from app.services.delivery import email_configured, slack_configured
from app.services.extraction import OPENAI_STYLE, PROVIDER_LABEL, provider, provider_key, provider_model
from app.services.meetstream import MeetStreamError, meetstream

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get("")
def status(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    teams = list(db.scalars(select(Team).order_by(Team.name)))
    return {
        "done": bool(get_setting(db, "onboarding_done")),
        "keys": saved_keys.describe(),
        "meetstream": meetstream.configured,
        "analysis_provider": provider(),
        "analysis_model": provider_model(),
        "voice_chosen": voices.chosen(db),
        "analysis": bool(provider_key()),
        "teams": [{"id": t.id, "name": t.name, "board_source": t.board_source or "native", "board_name": t.board_name}
                  for t in teams],
        "people": db.scalar(select(func.count(Employee.id)).where(Employee.active.is_(True))),
        "trello": trello_board.connected(db),
        "calendar": bool(get_setting(db, "calendar_connected")),
        "google_sign_in": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        "email": email_configured(),
        "slack": slack_configured(),
        "app_url": settings.APP_URL,
    }


@router.put("/keys")
def save_keys(values: Dict[str, Any], db: Session = Depends(get_db), _: User = Depends(require_admin)):
    unknown = set(values) - set(saved_keys.FIELDS)
    if unknown:
        raise HTTPException(400, f"Unknown setting: {', '.join(sorted(unknown))}")
    if "ANALYSIS_PROVIDER" in values and values["ANALYSIS_PROVIDER"] not in ("", "gemini", "anthropic", "openai", "xai"):
        raise HTTPException(400, "ANALYSIS_PROVIDER must be gemini, anthropic, openai or xai.")
    try:
        saved_keys.save(db, values)
    except ValueError:
        raise HTTPException(400, "SMTP_PORT must be a number.")
    return saved_keys.describe()


@router.post("/check/meetstream")
async def check_meetstream(_: User = Depends(require_admin)):
    if not meetstream.configured:
        raise HTTPException(400, "Add your MeetStream API key first.")
    try:  # a made-up bot: "not found" proves the key is accepted
        await meetstream.status("00000000-0000-0000-0000-000000000000")
    except MeetStreamError as exc:
        if exc.status in (401, 403):
            raise HTTPException(400, "MeetStream rejected the key. Copy it again from app.meetstream.ai.")
        if exc.status is None:
            raise HTTPException(502, str(exc))
    return {"message": "MeetStream accepted the key."}


@router.post("/check/analysis")
async def check_analysis(_: User = Depends(require_admin)):
    name = provider()
    label, key, model = PROVIDER_LABEL[name], provider_key(name), provider_model(name)
    if not key:
        raise HTTPException(400, f"Add your {label} API key first.")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            if name == "gemini":
                r = await client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                     headers={"x-goog-api-key": key}, params={"pageSize": 1000})
                ids = [m.get("name", "").removeprefix("models/") for m in (r.json().get("models") or [])] if r.status_code == 200 else []
            elif name == "anthropic":
                r = await client.get("https://api.anthropic.com/v1/models", params={"limit": 1000},
                                     headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
                ids = [m.get("id") for m in (r.json().get("data") or [])] if r.status_code == 200 else []
            else:
                r = await client.get(f"{OPENAI_STYLE[name][0]}/models", headers={"Authorization": f"Bearer {key}"})
                ids = [m.get("id") for m in (r.json().get("data") or [])] if r.status_code == 200 else []
    except httpx.HTTPError:
        raise HTTPException(502, f"Could not reach {label}. Check the network.")
    if r.status_code in (400, 401, 403):
        raise HTTPException(400, f"{label} rejected the key.")
    if r.status_code >= 400:
        raise HTTPException(400, f"{label} answered {r.status_code}.")
    # Model lists can omit aliases, so a missing model is a hint, not a failure.
    if ids and model not in ids:
        close = [i for i in ids if i and model.split("-")[0] in i][:6]
        return {"message": f"{label} accepted the key, but the model \"{model}\" isn't in its list"
                           + (f" (try: {', '.join(close)})" if close else "") + ". Change it under Model if analysis fails."}
    return {"message": f"{label} is ready ({model})."}


@router.get("/voices")
def list_voices(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.services import voices

    return voices.describe(db)


class VoiceChoice(BaseModel):
    provider: str
    voice: Optional[str] = None


@router.put("/voices")
def choose_voice(body: VoiceChoice, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.services import voices

    preset = voices.PRESETS.get(body.provider)
    if not preset:
        raise HTTPException(400, "Unknown voice provider.")
    voice = body.voice or preset["default_voice"]
    if voice not in {v["id"] for v in preset["voices"]} and body.provider != "claude":
        raise HTTPException(400, "That voice isn't available for this provider.")
    set_settings(db, {"standup_voice_provider": body.provider, "standup_voice": voice})
    return voices.describe(db)


@router.post("/voices/check")
async def check_voice(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.services import voices

    try:
        return {"message": await voices.check(db)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/done")
def finish(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    set_settings(db, {"onboarding_done": True})
    return {"done": True}
