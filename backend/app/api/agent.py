"""Endpoints the stand-up voice agent calls during a meeting (needs PUBLIC_URL).

MeetStream POSTs a custom-function call as {"name", "bot": {"bot_id"}, "args"}.
Auth is the same bearer token as the MCP endpoint.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, session_scope
from app.models import Meeting
from app.services.app_settings import get_setting
from app.services.meetstream import LIVE_STATES, MeetStreamError, meetstream

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])

# Give the goodbye time to finish playing before the bot drops out.
LEAVE_DELAY_SECONDS = 6


class FunctionCall(BaseModel):
    name: Optional[str] = None
    bot: Optional[Dict[str, Any]] = None
    args: Optional[Dict[str, Any]] = None


async def _leave_later(meeting_id: str, bot_id: str, reason: str) -> None:
    await asyncio.sleep(LEAVE_DELAY_SECONDS)
    try:
        await meetstream.remove_bot(bot_id)
    except MeetStreamError as exc:
        log.warning("Agent-requested leave failed for %s: %s", meeting_id, exc)
        return
    with session_scope() as db:
        m = db.get(Meeting, meeting_id)
        if m and not m.stop_reason:
            m.stop_reason = f"The stand-up agent closed the meeting ({reason})."


@router.post("/leave")
async def leave(body: FunctionCall, authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    token = get_setting(db, "mcp_token")
    scheme, _, supplied = (authorization or "").partition(" ")
    if not token or scheme.lower() != "bearer" or not hmac.compare_digest(supplied.strip(), token):
        raise HTTPException(401, "Invalid or missing bearer token")
    bot_id = (body.bot or {}).get("bot_id")
    if not bot_id:
        raise HTTPException(400, "bot.bot_id is required")
    meeting = db.scalar(select(Meeting).where(Meeting.bot_id == bot_id))
    # Only bots this install launched, still in a call, and only stand-up agents.
    if meeting is None or meeting.mode != "standup":
        raise HTTPException(404, "No stand-up meeting for this bot")
    if meeting.bot_status not in LIVE_STATES:
        return {"result": "Already left the meeting."}
    reason = str((body.args or {}).get("reason") or "stand-up finished")[:200]
    asyncio.create_task(_leave_later(meeting.id, bot_id, reason))
    return {"result": "Leaving the meeting now."}
