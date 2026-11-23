"""Calendar auto-join.

The calendar is connected through MeetStream (Google or Outlook OAuth
credentials go to MeetStream, not into this app's database). MeetStream keeps
the calendar synced; this module reads its upcoming events and books a bot
for each one through this app's own create_bot path, so calendar meetings
get the same consent notice, processing and progress tracking as scheduled
ones. MeetStream's own auto-scheduler is not used for that reason.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Meeting
from app.services.app_settings import get_setting
from app.services.meetstream import MeetStreamError, meetstream

log = logging.getLogger(__name__)


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalize_event(e: Dict[str, Any]) -> Dict[str, Any]:
    raw = e.get("raw") or {}
    return {
        "id": str(e.get("id")),
        "title": raw.get("summary") or raw.get("subject") or e.get("title") or "Calendar meeting",
        "start": _parse(e.get("start_time")),
        "end": _parse(e.get("end_time")),
        "meeting_url": e.get("meeting_url") or raw.get("hangoutLink") or "",
        "platform": e.get("meeting_platform") or "",
        "organizer": ((raw.get("organizer") or {}).get("email") or ""),
        "attendees": [a.get("email") for a in raw.get("attendees") or [] if isinstance(a, dict) and a.get("email")],
        "deleted": bool(e.get("is_deleted")),
        "meetstream_bots": len(e.get("bots") or []),
    }


def occurrence_key(event: Dict[str, Any]) -> str:
    return f"cal:{event['id']}:{event['start']:%Y%m%dT%H%M}"[:64]


def wanted(db: Session, event: Dict[str, Any]) -> bool:
    """Filters from Admin settings: include / exclude keywords on the title."""
    if event["deleted"] or not event["meeting_url"] or not event["start"]:
        return False
    title = event["title"].lower()
    include = [k.lower() for k in (get_setting(db, "calendar_include_keywords") or []) if k]
    exclude = [k.lower() for k in (get_setting(db, "calendar_exclude_keywords") or []) if k]
    if include and not any(k in title for k in include):
        return False
    return not any(k in title for k in exclude)


async def upcoming_events(hours: int = 72) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    out = []
    for raw in await meetstream.calendar_events():
        ev = normalize_event(raw)
        if ev["start"] and now - timedelta(minutes=30) <= ev["start"] <= now + timedelta(hours=hours):
            out.append(ev)
    return sorted(out, key=lambda e: e["start"])


def meeting_for_event(db: Session, event: Dict[str, Any], mode: str = "notetaker") -> Meeting:
    """Create (or return) the Meeting row for a calendar event."""
    key = occurrence_key(event)
    existing = db.scalar(select(Meeting).where(Meeting.occurrence_key == key))
    if existing:
        return existing
    m = Meeting(
        title=event["title"][:255],
        meeting_link=event["meeting_url"],
        mode=mode,
        occurrence_key=key,
        organizer_user_id=get_setting(db, "calendar_owner_user_id"),
        scheduled_at=event["start"],
        meeting_date=event["start"].date(),
        share_full=get_setting(db, "default_share_full"),
        share_employee=get_setting(db, "default_share_employee"),
    )
    db.add(m)
    db.flush()
    return m


async def sweep(db: Session) -> int:
    """Book bots for upcoming calendar meetings when auto-join is on."""
    if not get_setting(db, "calendar_auto_join") or not get_setting(db, "calendar_connected"):
        return 0
    from app.services import bots

    try:
        events = await upcoming_events(hours=1)
    except MeetStreamError as exc:
        log.warning("Calendar sync failed: %s", exc)
        return 0
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(minutes=settings.SCHEDULE_LEAD_MINUTES)
    booked = 0
    for ev in events:
        if not (now - timedelta(minutes=5) <= ev["start"] <= horizon) or not wanted(db, ev):
            continue
        if db.scalar(select(Meeting.id).where(Meeting.occurrence_key == occurrence_key(ev))):
            continue
        m = meeting_for_event(db, ev)
        db.commit()
        try:
            await bots.launch(db, m, join_at=ev["start"] if ev["start"] > now else None)
            booked += 1
        except Exception as exc:
            db.rollback()
            m = db.get(Meeting, m.id)
            m.bot_status, m.processing_status = "failed", "skipped"
            m.stop_reason = str(exc) if isinstance(exc, MeetStreamError) else "Could not send the bot. See server logs."
            db.commit()
    return booked
