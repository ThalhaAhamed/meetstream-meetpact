"""Recording consent: announce the bot, greet late joiners, honour opt-outs.

What MeetStream supports and this module relies on:
* ``send_message`` posts into the meeting chat (only once the bot is admitted:
  a message sent from the waiting room is lost, so the notice is sent after
  the bot reaches InMeeting - learned from meetstream-ai/companion).
* ``get_participants`` gives the roster; new names after the notice are late
  joiners and get their own notice.
* ``pause_recording`` / ``resume_recording`` open a privacy window without
  the bot leaving.
* ``get_chats`` returns the chat. Post-call it is used to find opt-outs and
  redact those people from the notes. During the call it is polled best
  effort; if the platform returns chat live, "pause recording" typed in chat
  pauses the bot.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import ConsentEvent, Meeting, MeetingParticipant, User
from app.services import identity
from app.services.app_settings import get_setting
from app.services.meetstream import MeetStreamError, meetstream

log = logging.getLogger(__name__)


def record(db: Session, meeting: Meeting, kind: str, detail: str = "", participant: Optional[str] = None, actor: str = "bot") -> None:
    db.add(ConsentEvent(meeting_id=meeting.id, kind=kind, detail=detail, participant=participant, actor=actor))


def _organizer_name(db: Session, meeting: Meeting) -> str:
    if meeting.organizer_user_id:
        user = db.get(User, meeting.organizer_user_id)
        if user:
            return user.name
    return "the meeting organizer"


def notice_text(db: Session, meeting: Meeting) -> str:
    return str(get_setting(db, "consent_notice")).format(
        bot_name=get_setting(db, "bot_name"), organizer=_organizer_name(db, meeting)
    )


async def send_notice(db: Session, meeting: Meeting) -> bool:
    """Post the recording notice once the bot is in the call."""
    if meeting.consent_notice_sent or not meeting.bot_id:
        return False
    # Register everyone already in the call, so they are not later mistaken
    # for late joiners.
    try:
        employees = identity.active_employees(db)
        for name in roster_names(await meetstream.participants(meeting.bot_id)):
            upsert_participant(db, meeting, name, employees)
    except MeetStreamError:
        pass
    try:
        await meetstream.send_message(meeting.bot_id, notice_text(db, meeting))
    except MeetStreamError as exc:
        log.warning("Could not post consent notice for %s: %s", meeting.id, exc)
        return False
    meeting.consent_notice_sent = True
    # Everyone already present has now seen the notice.
    for p in meeting.participants:
        p.notice_sent = True
    record(db, meeting, "notice_sent", "Recording notice posted in the meeting chat.")
    db.commit()
    return True


async def send_reminder_if_due(db: Session, meeting: Meeting) -> bool:
    """Re-post a short recording reminder every N minutes while recording."""
    minutes = int(get_setting(db, "consent_reminder_minutes") or 0)
    if minutes <= 0 or not meeting.consent_notice_sent or meeting.recording_paused or not meeting.bot_id:
        return False
    last = (
        db.query(ConsentEvent)
        .filter(ConsentEvent.meeting_id == meeting.id, ConsentEvent.kind.in_(["notice_sent", "reminder", "late_joiner_notice"]))
        .order_by(ConsentEvent.at.desc())
        .first()
    )
    last_at = last.at if last else None
    if last_at is not None and last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)
    if last_at and now() - last_at < timedelta(minutes=minutes):
        return False
    text = str(get_setting(db, "consent_reminder")).format(bot_name=get_setting(db, "bot_name"))
    try:
        await meetstream.send_message(meeting.bot_id, text)
    except MeetStreamError as exc:
        log.warning("Consent reminder failed for %s: %s", meeting.id, exc)
        return False
    record(db, meeting, "reminder", "Recording reminder re-posted for anyone who joined late.")
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
        notice_sent=False,
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


async def greet_late_joiners(db: Session, meeting: Meeting, names: List[str]) -> int:
    """Register names seen in the call; notify those who arrived after the notice."""
    employees = identity.active_employees(db)
    late: List[MeetingParticipant] = []
    for name in names:
        p, _ = upsert_participant(db, meeting, name, employees)
        if meeting.consent_notice_sent and not p.notice_sent and not p.is_bot:
            late.append(p)
    db.commit()
    if not late or not meeting.bot_id:
        return 0
    text = str(get_setting(db, "late_joiner_notice")).format(
        names=", ".join(p.display_name for p in late), bot_name=get_setting(db, "bot_name")
    )
    try:
        await meetstream.send_message(meeting.bot_id, text)
    except MeetStreamError as exc:
        log.warning("Late-joiner notice failed for %s: %s", meeting.id, exc)
        return 0
    for p in late:
        p.notice_sent = True
        p.joined_late = True
        record(db, meeting, "late_joiner_notice", "Notice posted for a participant who joined late.", participant=p.display_name)
    db.commit()
    return len(late)


# ---- chat commands -----------------------------------------------------------

def normalize_chats(payload: Any) -> List[Dict[str, str]]:
    """get_chats has no fixed schema across platforms; find author + text.

    Observed on Google Meet (live test, Nov 2026):
    {"metadata": {...}, "speakers": [{"deviceId", "name", ...}],
     "chatMessages": [{"messageId", "deviceId", "timestamp", "text"}]}
    Messages carry only a deviceId; the name comes from ``speakers``."""
    items: List[Any] = []
    names: Dict[str, str] = {}
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for s in payload.get("speakers") or []:
            if isinstance(s, dict) and s.get("deviceId"):
                names[s["deviceId"]] = s.get("name") or s.get("displayName") or ""
        for key in ("chatMessages", "chats", "messages", "chat_messages", "data", "results"):
            if isinstance(payload.get(key), list):
                items = payload[key]
                break
    out = []
    for m in items:
        if not isinstance(m, dict):
            continue
        author = (m.get("sender_name") or m.get("author") or m.get("sender") or m.get("name") or m.get("from")
                  or m.get("displayName") or names.get(m.get("deviceId") or "", "") or "")
        if isinstance(author, dict):
            author = author.get("name") or author.get("full_name") or author.get("displayName") or ""
        text = m.get("message") or m.get("text") or m.get("content") or m.get("body") or ""
        stamp = m.get("timestamp") or m.get("created_at") or m.get("time") or ""
        if isinstance(stamp, dict):
            stamp = stamp.get("absolute") or stamp.get("relative") or ""
        if text:
            out.append({"author": str(author), "text": str(text), "at": str(stamp)})
    return out


def _has(text: str, keywords: Iterable[str]) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in keywords)


async def apply_chat_commands(db: Session, meeting: Meeting, chats: List[Dict[str, str]], live: bool) -> None:
    """Act on opt-out / pause / resume messages.

    Opt-outs are idempotent and re-checked over the whole chat (post-call
    included). Pause/resume are commands: each message is acted on at most
    once, when first seen live, and a message that was a no-op at the time
    (e.g. "resume recording" while recording) is consumed, never replayed
    later. ``meeting.chat_cursor`` counts the messages already consumed."""
    seen = {(e.participant or "", e.detail) for e in db.query(ConsentEvent).filter_by(meeting_id=meeting.id)}
    opt_kw = get_setting(db, "opt_out_keywords")
    pause_kw = get_setting(db, "pause_keywords")
    resume_kw = get_setting(db, "resume_keywords")
    bot = get_setting(db, "bot_name")
    cursor = meeting.chat_cursor or 0
    for index, msg in enumerate(chats):
        author, text = msg["author"], msg["text"]
        if identity.is_bot_name(author) or author == bot:
            continue
        detail = f"Chat: \"{text[:200]}\""
        is_new_command = live and index >= cursor
        if _has(text, opt_kw):
            if (author, detail) in seen:
                continue
            p, _ = upsert_participant(db, meeting, author) if author else (None, False)
            if p:
                p.opted_out = True
            record(db, meeting, "opt_out", detail, participant=author or None, actor=author or "participant")
            seen.add((author, detail))
        elif is_new_command and _has(text, pause_kw) and not meeting.recording_paused and meeting.bot_id:
            try:
                await meetstream.pause_recording(meeting.bot_id)
                meeting.recording_paused = True
                meeting.bot_status = "paused"
                record(db, meeting, "paused", detail, participant=author or None, actor=author or "participant")
                await meetstream.send_message(meeting.bot_id, str(get_setting(db, "pause_ack")))
            except MeetStreamError as exc:
                log.warning("Pause from chat failed: %s", exc)
        elif is_new_command and _has(text, resume_kw) and meeting.recording_paused and meeting.bot_id:
            try:
                await meetstream.resume_recording(meeting.bot_id)
                meeting.recording_paused = False
                meeting.bot_status = "recording"
                record(db, meeting, "resumed", detail, participant=author or None, actor=author or "participant")
                await meetstream.send_message(meeting.bot_id, str(get_setting(db, "resume_ack")))
            except MeetStreamError as exc:
                log.warning("Resume from chat failed: %s", exc)
    if live:
        meeting.chat_cursor = max(cursor, len(chats))
    db.commit()


def opted_out_names(meeting: Meeting) -> set[str]:
    return {identity.norm(p.display_name) for p in meeting.participants if p.opted_out}


def now() -> datetime:
    return datetime.now(timezone.utc)
