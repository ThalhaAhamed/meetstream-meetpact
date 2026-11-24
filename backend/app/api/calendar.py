"""Calendar connection and calendar-driven bot booking."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers as S
from app.auth import current_user, require_admin, require_manager
from app.config import secret_key, settings
from app.db import get_db
from app.models import Meeting, Team, User
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
        "google_sign_in": google_sign_in_ready(),
        "google_redirect_uri": google_redirect_uri() if google_sign_in_ready() else None,
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


# ---- Google sign-in -----------------------------------------------------------
# The OAuth dance happens here so nobody has to produce a refresh token by
# hand. Only read-only scopes are asked for; the token goes to MeetStream
# (POST /calendar/create_calendar) and is not stored by this app.

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
STATE_MAX_AGE = 600


def google_sign_in_ready() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def google_redirect_uri() -> str:
    if settings.GOOGLE_REDIRECT_URI:
        return settings.GOOGLE_REDIRECT_URI
    if settings.app_url_is_public:
        return f"{settings.APP_URL.rstrip('/')}/api/calendar/google/callback"
    return f"http://localhost:{settings.PORT}/api/calendar/google/callback"


def _state_signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key(), salt="meetpact-google-oauth")


def _back_to_app(path: str = "/schedules", **query: str) -> RedirectResponse:
    path = path if path in ("/schedules", "/setup") else "/schedules"
    return RedirectResponse(f"{settings.APP_URL.rstrip('/')}{path}?{urlencode(query)}", status_code=303)


@router.get("/google/start")
def google_start(next: str = "/schedules", admin: User = Depends(require_admin)):
    if not google_sign_in_ready():
        raise HTTPException(400, "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first.")
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": google_redirect_uri(),
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",  # always return a refresh token
        "include_granted_scopes": "true",
        "state": _state_signer().dumps({"u": admin.id, "n": next if next in ("/schedules", "/setup") else "/schedules"}),
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), status_code=303)


@router.get("/google/callback")
async def google_callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db),
                          admin: User = Depends(require_admin)):
    try:
        signed = _state_signer().loads(state, max_age=STATE_MAX_AGE)
        if not isinstance(signed, dict) or signed.get("u") != admin.id:
            raise BadSignature("different user")
    except BadSignature:
        return _back_to_app(calendar_error="The sign-in link expired. Try again.")
    back = signed.get("n") or "/schedules"
    if error:
        return _back_to_app(back, calendar_error=f"Google sign-in was cancelled ({error}).")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code, "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": google_redirect_uri(), "grant_type": "authorization_code",
            })
    except httpx.HTTPError:
        return _back_to_app(back, calendar_error="Could not reach Google. Try again.")
    token = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    refresh = token.get("refresh_token")
    if resp.status_code != 200 or not refresh:
        detail = token.get("error_description") or token.get("error") or f"HTTP {resp.status_code}"
        return _back_to_app(back, calendar_error=f"Google did not return a refresh token: {detail}")
    try:
        await connect(ConnectBody(provider="google", client_id=settings.GOOGLE_CLIENT_ID,
                                  client_secret=settings.GOOGLE_CLIENT_SECRET, refresh_token=refresh), db, admin)
    except HTTPException as exc:
        return _back_to_app(back, calendar_error=str(exc.detail))
    return _back_to_app(back, calendar="connected")


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
    team_id: Optional[str] = None  # a stand-up host expects this team


@router.post("/events/{event_id}/join")
async def join_event(event_id: str, body: JoinBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Book the bot for one calendar event by hand."""
    from app.services import voices

    if body.mode == "standup" and not voices.chosen(db):
        raise HTTPException(400, voices.NO_VOICE)
    try:
        evs = await calendar_sync.upcoming_events(hours=24 * 14)
    except MeetStreamError as exc:
        raise HTTPException(502, str(exc))
    ev = next((e for e in evs if e["id"] == event_id), None)
    if not ev or not ev["meeting_url"]:
        raise HTTPException(404, "That event is not in the next two weeks or has no meeting link.")
    m = calendar_sync.meeting_for_event(db, ev, mode=body.mode)
    m.organizer_user_id = m.organizer_user_id or user.id
    if body.team_id and not m.bot_id and db.get(Team, body.team_id):
        m.team_id = body.team_id
    db.commit()
    now = datetime.now(timezone.utc)
    try:
        await bots.launch(db, m, join_at=ev["start"] if ev["start"] > now else None)
    except MeetStreamError as exc:
        m.bot_status, m.processing_status, m.stop_reason = "failed", "skipped", str(exc)
        db.commit()
        raise HTTPException(502, str(exc))
    return S.meeting_brief(m)
