"""Endpoints the stand-up voice agent calls during a meeting (needs PUBLIC_URL).

MeetStream POSTs a custom-function call as {"name", "bot": {"bot_id"}, "args"}.
Auth is the same bearer token as the MCP endpoint.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, session_scope
from app.models import Meeting
from app.services import standup
from app.services.app_settings import get_setting
from app.services.meetstream import NotReady, LIVE_STATES, MeetStreamError, meetstream

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])

# The agent often calls the leave tool as it starts its recap, not after the
# goodbye, so give the closing words time to finish playing before it drops out.
LEAVE_DELAY_SECONDS = 20


class FunctionCall(BaseModel):
    name: Optional[str] = None
    bot: Optional[Dict[str, Any]] = None
    args: Optional[Dict[str, Any]] = None


async def _leave_later(meeting_id: str, bot_id: str, reason: str) -> None:
    await asyncio.sleep(LEAVE_DELAY_SECONDS)
    try:
        await meetstream.remove_bot(bot_id)
    except NotReady:
        pass  # 202: MeetStream accepted the request and the bot is leaving
    except MeetStreamError as exc:
        log.warning("Agent-requested leave failed for %s: %s", meeting_id, exc)
        return
    with session_scope() as db:
        m = db.get(Meeting, meeting_id)
        if m and (not m.stop_reason or m.stop_reason == "The bot left normally."):
            m.stop_reason = f"The stand-up agent closed the meeting ({reason})."


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _arrived_first(meeting: Meeting) -> bool:
    """A signed-in bot was in the call by the start time (it joins early), so
    MeetStream sent a join event for everyone who came after it. A guest bot
    knocks, so whoever let it in was already there and is never reported."""
    from app.services.bots import google_sign_in_block

    if not google_sign_in_block(meeting.meeting_link):
        return False
    started, scheduled = _aware(meeting.started_at), _aware(meeting.scheduled_at)
    return bool(started and scheduled and started <= scheduled)


def _standup_meeting(body: FunctionCall, authorization: Optional[str], db: Session) -> Meeting:
    token = get_setting(db, "mcp_token")
    scheme, _, supplied = (authorization or "").partition(" ")
    if not token or scheme.lower() != "bearer" or not hmac.compare_digest(supplied.strip(), token):
        raise HTTPException(401, "Invalid or missing bearer token")
    bot_id = (body.bot or {}).get("bot_id")
    if not bot_id:
        raise HTTPException(400, "bot.bot_id is required")
    meeting = db.scalar(select(Meeting).where(Meeting.bot_id == bot_id))
    # Only bots this install launched, and only stand-up agents.
    if meeting is None or meeting.mode != "standup":
        raise HTTPException(404, "No stand-up meeting for this bot")
    return meeting


@router.post("/participants")
def participants(body: FunctionCall, authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    """Who has come and gone since the agent joined, from participant_events
    webhooks. A signed-in bot that got there first sees everyone, so the agent
    asks only them. Otherwise people already in the call when the bot arrived
    are never reported, so the agent asks those it saw join (in join order)
    and then the rest of the expected team."""
    meeting = _standup_meeting(body, authorization, db)
    people = [p for p in meeting.participants if not p.is_bot]
    name = lambda p: p.employee.name if p.employee else p.display_name
    joined = [name(p) for p in people if p.last_left_at is None]
    left = [name(p) for p in people if p.last_left_at is not None]
    if _arrived_first(meeting):
        # The bot was in before the start time, so every join was seen.
        here = {p.employee_id for p in people if p.employee_id and p.last_left_at is None}
        missing = [e.name for e in standup.roster(db, meeting) if e.id not in here]
        parts = ["In the call now: " + (", ".join(joined) if joined else "nobody yet") + "."]
        if missing:
            parts.append("Expected but not in the call: " + ", ".join(missing) + ". Do not call on them unless they join.")
        parts.append("This is for you only: never mention this list or tool aloud.")
        return {"result": " ".join(parts)}
    parts = []
    if joined:
        parts.append("Joined since you arrived: " + ", ".join(joined) + ".")
    if left:
        parts.append("Left the call: " + ", ".join(left) + ".")
    if not parts:
        parts.append("Nobody has joined or left since you arrived.")
    seen = {p.employee_id for p in people if p.employee_id}
    rest = [e.name for e in standup.roster(db, meeting) if e.id not in seen]
    if rest:
        parts.append("Then ask the rest of the expected people: " + ", ".join(rest) + ".")
    parts.append("People who were already in the call when you joined are not listed, so ask the people who "
                 "joined first, in that order, then go through the rest by name and skip anyone who does not "
                 "answer. This is for you only: never mention this list or tool aloud.")
    return {"result": " ".join(parts)}


@router.post("/leave")
async def leave(body: FunctionCall, authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    meeting = _standup_meeting(body, authorization, db)
    bot_id = meeting.bot_id
    if meeting.bot_status not in LIVE_STATES:
        return {"result": "Already left the meeting."}
    reason = str((body.args or {}).get("reason") or "stand-up finished")[:200]
    asyncio.create_task(_leave_later(meeting.id, bot_id, reason))
    return {"result": "Leaving the meeting now."}
