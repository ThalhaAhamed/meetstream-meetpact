"""Calendar connection and calendar-driven bot booking."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers as S
from app.auth import current_user, require_admin, require_manager
from app.db import get_db
from app.models import Meeting, User
from app.services import bots, calendar_sync
from app.services.app_settings import get_setting, set_settings
from app.services.meetstream import MeetStreamError, meetstream

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("")
async def status(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {
        "connected": bool(get_setting(db, "calendar_connected")),
        "account": get_setting(db, "calendar_account"),
        "auto_join": bool(get_setting(db, "calendar_auto_join")),
        "include_keywords": get_setting(db, "calendar_include_keywords"),
        "exclude_keywords": get_setting(db, "calendar_exclude_keywords"),
    }


class ConnectBody(BaseModel):
    provider: str = "google"  # google | outlook
    client_id: str = Field(min_length=3)
    client_secret: str = Field(min_length=3)
    refresh_token: str = Field(min_length=3)


@router.post("/connect")
async def connect(body: ConnectBody, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """The OAuth credentials are passed straight to MeetStream and not stored here."""
    try:
        if body.provider == "outlook":
            resp = await meetstream.connect_outlook_calendar(body.client_id, body.client_secret, body.refresh_token)
        else:
            resp = await meetstream.connect_google_calendar(body.client_id, body.client_secret, body.refresh_token)
    except MeetStreamError as exc:
        raise HTTPException(502, str(exc))
    account = resp.get("user_email") or resp.get("account_id") or resp.get("email") or body.provider
    set_settings(db, {"calendar_connected": True, "calendar_account": account, "calendar_owner_user_id": admin.id})
    return {"connected": True, "account": account}


@router.delete("")
async def disconnect(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        await meetstream.disconnect_calendar()
    except MeetStreamError as exc:
        raise HTTPException(502, str(exc))
    set_settings(db, {"calendar_connected": False, "calendar_account": None, "calendar_auto_join": False})
    return {"connected": False}


class AutoJoinBody(BaseModel):
    auto_join: bool
    include_keywords: list[str] = []
    exclude_keywords: list[str] = []


@router.put("/auto-join")
def auto_join(body: AutoJoinBody, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    set_settings(db, {"calendar_auto_join": body.auto_join, "calendar_include_keywords": body.include_keywords,
                      "calendar_exclude_keywords": body.exclude_keywords})
    return {"ok": True}


@router.get("/events")
async def events(hours: int = 72, db: Session = Depends(get_db), _: User = Depends(current_user)):
    if not get_setting(db, "calendar_connected"):
        return []
    try:
        evs = await calendar_sync.upcoming_events(hours=min(hours, 24 * 14))
    except MeetStreamError as exc:
        raise HTTPException(502, str(exc))
    out = []
    for ev in evs:
        m = db.scalar(select(Meeting).where(Meeting.occurrence_key == calendar_sync.occurrence_key(ev)))
        out.append({**{k: v for k, v in ev.items() if k not in ("start", "end")},
                    "start": S.iso(ev["start"]), "end": S.iso(ev["end"]),
                    "auto_join_match": calendar_sync.wanted(db, ev),
                    "meeting": S.meeting_brief(m) if m else None})
    return out


class JoinBody(BaseModel):
    mode: str = "notetaker"


@router.post("/events/{event_id}/join")
async def join_event(event_id: str, body: JoinBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Book the bot for one calendar event by hand."""
    try:
        evs = await calendar_sync.upcoming_events(hours=24 * 14)
    except MeetStreamError as exc:
        raise HTTPException(502, str(exc))
    ev = next((e for e in evs if e["id"] == event_id), None)
    if not ev or not ev["meeting_url"]:
        raise HTTPException(404, "That event is not in the next two weeks or has no meeting link.")
    m = calendar_sync.meeting_for_event(db, ev, mode=body.mode)
    m.organizer_user_id = m.organizer_user_id or user.id
    db.commit()
    now = datetime.now(timezone.utc)
    try:
        await bots.launch(db, m, join_at=ev["start"] if ev["start"] > now + timedelta(seconds=90) else None)
    except MeetStreamError as exc:
        m.bot_status, m.processing_status, m.stop_reason = "failed", "skipped", str(exc)
        db.commit()
        raise HTTPException(502, str(exc))
    return S.meeting_brief(m)
