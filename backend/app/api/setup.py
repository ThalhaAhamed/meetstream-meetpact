"""The setup wizard: what is configured, saving keys, and live checks."""
from __future__ import annotations

from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import settings
from app.db import get_db
from app.models import Employee, Team, User
from app.services import saved_keys, trello_board
from app.services.app_settings import get_setting, set_settings
from app.services.delivery import email_configured, slack_configured
from app.services.extraction import provider
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
        "analysis": bool(settings.GEMINI_API_KEY if provider() == "gemini" else settings.ANTHROPIC_API_KEY),
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
    if "ANALYSIS_PROVIDER" in values and values["ANALYSIS_PROVIDER"] not in ("", "gemini", "anthropic"):
        raise HTTPException(400, "ANALYSIS_PROVIDER must be gemini or anthropic.")
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
    try:
        if provider() == "gemini":
            if not settings.GEMINI_API_KEY:
                raise HTTPException(400, "Add your Gemini API key first.")
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                     headers={"x-goog-api-key": settings.GEMINI_API_KEY}, params={"pageSize": 1})
            if r.status_code >= 400:
                raise HTTPException(400, "Google rejected the Gemini key." if r.status_code in (400, 401, 403)
                                    else f"Gemini answered {r.status_code}.")
            return {"message": f"Gemini is ready ({settings.GEMINI_MODEL})."}
        if not settings.ANTHROPIC_API_KEY:
            raise HTTPException(400, "Add your Claude API key first.")
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get("https://api.anthropic.com/v1/models", params={"limit": 1},
                                 headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"})
        if r.status_code >= 400:
            raise HTTPException(400, "Anthropic rejected the Claude key." if r.status_code in (401, 403)
                                else f"Anthropic answered {r.status_code}.")
        return {"message": f"Claude is ready ({settings.ANALYSIS_MODEL})."}
    except httpx.HTTPError:
        raise HTTPException(502, "Could not reach the AI provider. Check the network.")


@router.post("/done")
def finish(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    set_settings(db, {"onboarding_done": True})
    return {"done": True}
