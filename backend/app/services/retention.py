"""Data retention and deletion.

* purge_expired: transcripts older than `transcript_retention_days` are
  deleted here and the recording/transcript are deleted at MeetStream
  (DELETE /bots/{id}/delete). The report, updates and work items stay.
* delete_media: the same for one meeting, on demand.
* erase_employee: removes everything recorded about one person.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Blocker,
    ConsentEvent,
    Employee,
    EmployeeUpdate,
    Meeting,
    MeetingParticipant,
    TranscriptSegment,
    User,
    WorkItem,
)
from app.services.app_settings import get_setting
from app.services.meetstream import MeetStreamError, meetstream

log = logging.getLogger(__name__)


async def delete_media(db: Session, meeting: Meeting, actor: str = "retention") -> Dict[str, bool]:
    """Delete the transcript here and the recording + transcript at MeetStream."""
    result = {"local": False, "meetstream": False}
    for seg in list(meeting.segments):
        db.delete(seg)
    result["local"] = True
    if meeting.bot_id and meetstream.configured:
        try:
            await meetstream.delete_bot_data(meeting.bot_id)
            result["meetstream"] = True
        except MeetStreamError as exc:
            log.warning("MeetStream data deletion failed for %s: %s", meeting.id, exc)
    meeting.media_deleted_at = datetime.now(timezone.utc)
    db.add(ConsentEvent(meeting_id=meeting.id, kind="data_deleted", actor=actor,
                        detail="Transcript deleted" + (" and recording deleted at MeetStream." if result["meetstream"] else ".")))
    db.commit()
    return result


async def purge_expired(db: Session) -> int:
    days = int(get_setting(db, "transcript_retention_days") or 0)
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    due = list(db.scalars(select(Meeting).where(
        Meeting.media_deleted_at.is_(None),
        Meeting.processing_status.in_(["done", "failed", "skipped"]),
        Meeting.created_at < cutoff,
    )))
    for m in due:
        await delete_media(db, m)
    return len(due)


def erase_employee(db: Session, employee_id: str, actor: str) -> Dict[str, int]:
    """Remove a person's records: updates, work items, blockers, transcript
    lines and the employee profile itself. Meeting reports keep their summary
    text, which may still mention them by name - re-analyse a meeting after
    erasing if that matters."""
    emp = db.get(Employee, employee_id)
    if emp is None:
        return {}
    counts = {
        "updates": db.query(EmployeeUpdate).filter_by(employee_id=employee_id).delete(),
        "work_items": db.query(WorkItem).filter_by(employee_id=employee_id).delete(),
        "blockers": db.query(Blocker).filter_by(employee_id=employee_id).delete(),
        "transcript_lines": 0,
    }
    names = {emp.name, *(emp.aliases or [])}
    for p in db.scalars(select(MeetingParticipant).where(MeetingParticipant.employee_id == employee_id)):
        names.add(p.display_name)
        db.delete(p)
    for seg in db.scalars(select(TranscriptSegment).where(
            (TranscriptSegment.employee_id == employee_id) | TranscriptSegment.speaker.in_(names))):
        seg.speaker, seg.text, seg.employee_id, seg.redacted = "Removed person", "[removed]", None, True
        counts["transcript_lines"] += 1
    for u in db.scalars(select(User).where(User.employee_id == employee_id)):
        u.employee_id = None
    db.delete(emp)
    db.commit()
    log.info("Employee %s erased by %s: %s", employee_id, actor, counts)
    return counts
