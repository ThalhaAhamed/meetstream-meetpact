"""MeetStream webhook receivers (only reachable when PUBLIC_URL is set up).

* ``/api/webhooks/meetstream``: lifecycle events (callback_url).
* ``/api/webhooks/participants``: participant_events.join / .leave
  (recording_config.realtime_endpoints).

MeetStream does not retry deliveries, so both ACK quickly and do the work in
a background task. Deliveries are deduplicated on bot_id + event + timestamp.
Per-bot callback deliveries are not signed; a signature is verified when one
is present and MEETSTREAM_WEBHOOK_SECRET is set. Unsigned events are only
accepted for bots this install launched.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.config import settings
from app.db import session_scope
from app.models import Meeting, WebhookDelivery
from app.services import consent
from app.services.meetstream import STOP_REASONS, stop_reason
from app.services.workers import apply_status, run_processing

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

LIFECYCLE = {
    "bot.joining": "joining",
    "bot.in_waiting_room": "waiting_room",
    "bot.inmeeting": "in_meeting",
    "bot.recording": "recording",
}


def _verify(raw: bytes, request: Request) -> None:
    sig = request.headers.get("X-MeetStream-Signature")
    if not sig or not settings.MEETSTREAM_WEBHOOK_SECRET:
        return
    expected = hmac.new(settings.MEETSTREAM_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    candidate = sig[7:] if sig.startswith("sha256=") else sig
    if not hmac.compare_digest(expected, candidate.strip()):
        raise HTTPException(401, "Bad signature")


def _claim(key: str) -> bool:
    with session_scope() as db:
        if db.get(WebhookDelivery, key):
            return False
        db.add(WebhookDelivery(key=key))
    return True


def _meeting_id_for(bot_id: Optional[str], attrs: Dict[str, Any]) -> Optional[str]:
    with session_scope() as db:
        if bot_id:
            mid = db.scalar(select(Meeting.id).where(Meeting.bot_id == bot_id))
            if mid:
                return mid
        mid = (attrs or {}).get("meeting_id")
        if mid and db.get(Meeting, mid) and not db.get(Meeting, mid).bot_id:
            return mid
    return None


async def _handle_lifecycle(event: Dict[str, Any]) -> None:
    bot_id = event.get("bot_id")
    meeting_id = _meeting_id_for(bot_id, event.get("custom_attributes") or {})
    if not meeting_id:
        return
    name = event.get("bot_event") or event.get("event")
    if event.get("event") == "bot.stopped":
        reason = stop_reason(event)
        status, text = STOP_REASONS.get(reason, ("ended", event.get("message") or "Bot stopped."))
        await apply_status(meeting_id, status, text)
    elif name in LIFECYCLE:
        await apply_status(meeting_id, LIFECYCLE[name])
    elif name in ("transcription.processed", "bot.transcriptionready", "bot.done"):
        with session_scope() as db:
            m = db.get(Meeting, meeting_id)
            ready = m and m.bot_status == "ended" and m.processing_status == "waiting"
        if ready:
            await run_processing(meeting_id)
    elif name == "transcription.failed":
        with session_scope() as db:
            m = db.get(Meeting, meeting_id)
            if m and m.processing_status in ("waiting", "fetching"):
                m.processing_status = "failed"
                m.processing_error = "MeetStream could not transcribe this meeting. Import a transcript instead."


@router.post("/meetstream")
async def meetstream_webhook(request: Request):
    raw = await request.body()
    _verify(raw, request)
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Malformed JSON")
    if not isinstance(event, dict) or not event.get("event"):
        raise HTTPException(400, "Missing event")
    key = f"{event.get('bot_id')}:{event.get('bot_event') or event.get('event')}:{event.get('timestamp') or hashlib.sha1(raw).hexdigest()}"
    if not _claim(key):
        return {"ok": True, "duplicate": True}
    asyncio.create_task(_safe(_handle_lifecycle(event)))
    return {"ok": True}


async def _handle_participant(event: Dict[str, Any]) -> None:
    data = (event.get("data") or {})
    inner = data.get("data") or {}
    bot_id = (data.get("bot") or {}).get("id")
    meeting_id = _meeting_id_for(bot_id, event.get("custom_attributes") or {})
    if not meeting_id:
        return
    action = inner.get("action") or str(event.get("event", "")).split(".")[-1]
    p = inner.get("participant") or {}
    name = p.get("full_name") or p.get("name")
    if not name:
        return
    with session_scope() as db:
        meeting = db.get(Meeting, meeting_id)
        if action == "join":
            part, _ = consent.upsert_participant(db, meeting, name)
            part.last_left_at = None  # a rejoin counts as present again
        elif action == "leave":
            part, _ = consent.upsert_participant(db, meeting, name)
            part.last_left_at = consent.now()


@router.post("/participants")
async def participant_webhook(request: Request):
    raw = await request.body()
    _verify(raw, request)
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Malformed JSON")
    inner = ((event.get("data") or {}).get("data") or {})
    key = f"p:{((event.get('data') or {}).get('bot') or {}).get('id')}:{event.get('event')}:{(inner.get('participant') or {}).get('id')}:{event.get('timestamp')}"
    if not _claim(key):
        return {"ok": True, "duplicate": True}
    asyncio.create_task(_safe(_handle_participant(event)))
    return {"ok": True}


async def _safe(coro):
    try:
        await coro
    except Exception:
        log.exception("webhook handler failed")
