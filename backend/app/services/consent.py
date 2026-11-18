"""The recording notice, the meeting's activity log, and who was in the call.

Kept deliberately simple: when the bot is admitted it posts one short notice
in the meeting chat saying it is recording (a message sent from the waiting
room is lost, so it waits for InMeeting - learned from meetstream-ai/companion).
The organizer can pause, resume or remove the bot from the dashboard.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import ConsentEvent, Meeting, MeetingParticipant, User
from app.services import identity
from app.services.app_settings import get_setting
from app.services.meetstream import MeetStreamError, meetstream

log = logging.getLogger(__name__)


def record(db: Session, meeting: Meeting, kind: str, detail: str = "", participant: Optional[str] = None, actor: str = "bot") -> None:
    """Add an entry to the meeting's activity log (notice, paused, resumed, removed, ...)."""
    db.add(ConsentEvent(meeting_id=meeting.id, kind=kind, detail=detail, participant=participant, actor=actor))


def _organizer_name(db: Session, meeting: Meeting) -> str:
    if meeting.organizer_user_id:
        user = db.get(User, meeting.organizer_user_id)
        if user:
            return user.name
    return "the meeting organizer"


def notice_text(db: Session, meeting: Meeting) -> str:
    return str(get_setting(db, "consent_notice") or "").format(
        bot_name=get_setting(db, "bot_name"), organizer=_organizer_name(db, meeting)
    ).strip()


_notice_in_flight: set = set()


async def send_notice(db: Session, meeting: Meeting) -> bool:
    """Post the recording notice once the bot is in the call. The lifecycle
    webhook and the status poller can both get here at the same moment, so a
    meeting being handled already is skipped. An empty notice turns it off."""
    if meeting.consent_notice_sent or not meeting.bot_id or meeting.id in _notice_in_flight:
        return False
    _notice_in_flight.add(meeting.id)
    try:
        return await _send_notice(db, meeting)
    finally:
        _notice_in_flight.discard(meeting.id)


async def _send_notice(db: Session, meeting: Meeting) -> bool:
    db.refresh(meeting)
    if meeting.consent_notice_sent:
        return False
    text = notice_text(db, meeting)
    if text:
        try:
            await meetstream.send_message(meeting.bot_id, text)
        except MeetStreamError as exc:
            log.warning("Could not post the recording notice for %s: %s", meeting.id, exc)
            return False
        record(db, meeting, "notice_sent", "Recording notice posted in the meeting chat.")
    meeting.consent_notice_sent = True
    db.commit()
    return True


def upsert_participant(
    db: Session, meeting: Meeting, name: str, employees=None, from_roster: bool = True
) -> Tuple[MeetingParticipant, bool]:
    """Find or add a participant. ``from_roster=False`` (a transcript speaker
    name) never marks someone as a late joiner: we did not see them arrive."""
    name = (name or "").strip()
    for p in meeting.participants:
        if p.display_name == name:
            return p, False
    employees = employees if employees is not None else identity.active_employees(db)
    emp = identity.match_employee(name, employees)
    p = MeetingParticipant(
        meeting_id=meeting.id,
        display_name=name,
        employee_id=emp.id if emp else None,
        mapping="auto" if emp else "unmatched",
        is_bot=identity.is_bot_name(name),
        joined_late=from_roster and meeting.consent_notice_sent,
    )
    meeting.participants.append(p)
    db.flush()
    return p, True


def roster_names(roster: Iterable[Dict[str, Any]]) -> List[str]:
    names = []
    for r in roster:
        if not isinstance(r, dict):
            continue
        # `status` is numeric; the readable state is in `humanized_status`.
        status = str(r.get("humanized_status") or "").lower()
        if any(word in status for word in ("left", "inactive", "removed")):
            continue
        name = r.get("fullName") or r.get("displayName") or r.get("full_name") or r.get("name")
        if name:
            names.append(str(name))
    return names


def register_participants(db: Session, meeting: Meeting, names: List[str]) -> None:
    """Record names seen in the call (live roster or participant webhooks)."""
    employees = identity.active_employees(db)
    for name in names:
        upsert_participant(db, meeting, name, employees)
    db.commit()


def now() -> datetime:
    return datetime.now(timezone.utc)
