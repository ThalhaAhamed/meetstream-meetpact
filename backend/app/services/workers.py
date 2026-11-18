"""Background loops: the scheduler and the bot watcher.

The watcher keeps meetings current by polling MeetStream, so the whole flow
works on a laptop with no public URL. When PUBLIC_URL is set, webhooks
arrive as well and simply get there first; both paths are idempotent.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import or_, select

from app.config import settings
from app.db import session_scope
from app.models import Meeting, Schedule
from app.services import bots, consent, recurrence
from app.services.app_settings import get_setting
from app.services.meetstream import (
    FINISHED_STATES,
    IN_CALL_STATES,
    MeetStreamError,
    NotReady,
    map_remote_status,
    meetstream,
)

log = logging.getLogger(__name__)

WATCH_SECONDS = 15
SCHEDULER_SECONDS = 30
TRANSCRIPT_RETRY_SECONDS = 60
_last_transcript_try: Dict[str, float] = {}
_processing: set[str] = set()


def _aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Status transitions (shared by watcher and webhooks)
# ---------------------------------------------------------------------------

async def apply_status(meeting_id: str, new_status: str, reason: str | None = None) -> None:
    with session_scope() as db:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or meeting.bot_status in FINISHED_STATES:
            return
        if meeting.recording_paused and new_status == "recording":
            new_status = "paused"
        if new_status == meeting.bot_status:
            return
        now = datetime.now(timezone.utc)
        if new_status in IN_CALL_STATES and not meeting.started_at:
            meeting.started_at = now
        meeting.bot_status = new_status
        if new_status in FINISHED_STATES:
            meeting.ended_at = meeting.ended_at or now
            if reason:
                meeting.stop_reason = reason
            if new_status in ("not_admitted", "denied", "failed"):
                meeting.processing_status = "skipped"
                if new_status == "denied":
                    consent.record(db, meeting, "denied", reason or "Host refused the bot.")
            else:
                meeting.processing_status = "waiting"
        db.commit()
        if new_status in IN_CALL_STATES and not meeting.consent_notice_sent:
            # Posted once the bot is admitted (a message sent from the waiting
            # room is lost).
            await consent.send_notice(db, meeting)
        if new_status in FINISHED_STATES and meeting.mia_agent_id:
            await bots.cleanup_agent(db, meeting)


async def _watch_one(meeting_id: str) -> None:
    with session_scope() as db:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or not meeting.bot_id:
            return
        bot_id = meeting.bot_id
        status = meeting.bot_status
        scheduled_at = _aware(meeting.scheduled_at)
    if status == "scheduled" and scheduled_at and scheduled_at > datetime.now(timezone.utc) + timedelta(minutes=1):
        return
    try:
        remote = await meetstream.status(bot_id)
    except MeetStreamError as exc:
        log.debug("status poll failed for %s: %s", bot_id, exc)
        return
    mapped = map_remote_status(remote)
    if mapped:
        await apply_status(meeting_id, mapped, None if mapped not in FINISHED_STATES else f"MeetStream status: {remote}")

    with session_scope() as db:
        meeting = db.get(Meeting, meeting_id)
        if meeting.bot_status not in IN_CALL_STATES:
            return
        # Who is in the call. MeetStream usually answers 404 here until the call
        # ends; participant webhooks (with a public URL) fill this in live.
        try:
            names = consent.roster_names(await meetstream.participants(bot_id))
            if names:
                consent.register_participants(db, meeting, names)
        except (MeetStreamError, NotReady):
            pass


async def run_processing(meeting_id: str) -> None:
    if meeting_id in _processing:
        return
    _processing.add(meeting_id)
    try:
        from app.services.processing import process_meeting

        await process_meeting(meeting_id)
    finally:
        _processing.discard(meeting_id)


async def watch_sweep() -> None:
    if not meetstream.configured:
        return
    with session_scope() as db:
        live_ids = list(
            db.scalars(
                select(Meeting.id).where(
                    Meeting.bot_id.is_not(None),
                    Meeting.bot_status.in_(["scheduled", "joining", "waiting_room", "in_meeting", "recording", "paused"]),
                )
            )
        )
        waiting_ids = list(
            db.scalars(
                select(Meeting.id).where(
                    Meeting.bot_id.is_not(None),
                    Meeting.bot_status == "ended",
                    Meeting.processing_status.in_(["waiting"]),
                )
            )
        )
    for mid in live_ids:
        try:
            await _watch_one(mid)
        except Exception:
            log.exception("watcher failed for meeting %s", mid)
    now = _time.monotonic()
    for mid in waiting_ids[:3]:
        if now - _last_transcript_try.get(mid, 0) < TRANSCRIPT_RETRY_SECONDS:
            continue
        _last_transcript_try[mid] = now
        asyncio.create_task(run_processing(mid))


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

async def schedule_sweep() -> None:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(minutes=settings.SCHEDULE_LEAD_MINUTES)
    to_launch = []
    with session_scope() as db:
        for sch in db.scalars(select(Schedule).where(Schedule.active.is_(True))):
            # Look back 5 minutes so a server restart just after start time still joins.
            for t in recurrence.occurrences(sch, now - timedelta(minutes=5), horizon):
                key = recurrence.occurrence_key(sch.id, t)
                if db.scalar(select(Meeting.id).where(Meeting.occurrence_key == key)):
                    continue
                m = Meeting(
                    title=sch.title,
                    meeting_link=sch.meeting_link,
                    mode=sch.mode,
                    slot=sch.slot,
                    schedule_id=sch.id,
                    occurrence_key=key,
                    team_id=sch.team_id,
                    project_id=sch.project_id,
                    organizer_user_id=sch.organizer_user_id,
                    scheduled_at=t,
                    meeting_date=recurrence.local_date(sch.timezone, t),
                    share_full=sch.share_full or get_setting(db, "default_share_full"),
                    share_employee=sch.share_employee or get_setting(db, "default_share_employee"),
                )
                db.add(m)
                db.flush()
                to_launch.append((m.id, t))
            if sch.recurrence == "once" and sch.start_date < now.date() - timedelta(days=1):
                sch.active = False
    for mid, t in to_launch:
        with session_scope() as db:
            m = db.get(Meeting, mid)
            try:
                await bots.launch(db, m, join_at=t if t > datetime.now(timezone.utc) + timedelta(seconds=90) else None)
            except Exception as exc:  # one failed launch must not strand the rest
                if not isinstance(exc, MeetStreamError):
                    log.exception("Unexpected error launching %s", mid)
                db.rollback()
                m = db.get(Meeting, mid)
                m.bot_status = "failed"
                m.processing_status = "skipped"
                m.stop_reason = str(exc) if isinstance(exc, MeetStreamError) else "Could not send the bot. See server logs."
                db.commit()
                log.warning("Scheduled launch failed for %s: %s", mid, exc)


async def _loop(fn, seconds: int, name: str) -> None:
    while True:
        try:
            await fn()
        except Exception:
            log.exception("%s sweep failed", name)
        await asyncio.sleep(seconds)


async def calendar_sweep() -> None:
    if not meetstream.configured:
        return
    from app.services import calendar_sync

    with session_scope() as db:
        await calendar_sync.sweep(db)


async def housekeeping_sweep() -> None:
    from app.services import retention

    with session_scope() as db:
        await retention.purge_expired(db)


def start_workers() -> list[asyncio.Task]:
    return [
        asyncio.create_task(_loop(schedule_sweep, SCHEDULER_SECONDS, "scheduler")),
        asyncio.create_task(_loop(watch_sweep, WATCH_SECONDS, "watcher")),
        asyncio.create_task(_loop(calendar_sweep, 120, "calendar")),
        asyncio.create_task(_loop(housekeeping_sweep, 3600, "housekeeping")),
    ]
