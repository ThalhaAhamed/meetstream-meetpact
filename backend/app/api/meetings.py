"""Meetings, live bot controls, sharing, transcript import, and schedules."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import access
from app.api import serializers as S
from app.auth import current_user, require_manager
from app.config import settings
from app.db import get_db
from app.models import ConsentEvent, Employee, EmployeeUpdate, Meeting, MeetingParticipant, Schedule, TranscriptSegment, User
from app.services import bots, recurrence
from app.services.app_settings import get_setting
from app.services.meetstream import LIVE_STATES, MeetStreamError, meetstream
from app.services.reports import employee_section_md, render_meeting_report
from app.services.transcript import parse_plain_transcript
from app.services.workers import run_processing

router = APIRouter(prefix="/api", tags=["meetings"])


class Share(BaseModel):
    audience: str = "participants"
    user_ids: List[str] = []


def _share(value: Optional[Share], db: Session, key: str) -> dict:
    if value is None:
        return get_setting(db, key)
    if value.audience not in access.AUDIENCES:
        raise HTTPException(400, f"audience must be one of {', '.join(access.AUDIENCES)}")
    return value.model_dump()


def _get(db: Session, meeting_id: str) -> Meeting:
    m = db.get(Meeting, meeting_id)
    if m is None:
        raise HTTPException(404, "Meeting not found.")
    return m


# ---- list / detail -------------------------------------------------------------

@router.get("/meetings")
def list_meetings(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    status: Optional[str] = None,
    employee_id: Optional[str] = None,
    limit: int = 200,
):
    q = (select(Meeting).options(selectinload(Meeting.participants))
         .order_by(Meeting.created_at.desc()).limit(min(limit, 500)))
    out = []
    for m in db.scalars(q):
        if status == "live" and m.bot_status not in LIVE_STATES | {"scheduled"}:
            continue
        if status and status != "live" and m.processing_status != status:
            continue
        if employee_id and employee_id not in {p.employee_id for p in m.participants}:
            continue
        if not access.can_view_meeting_at_all(db, user, m):
            continue
        d = S.meeting_brief(m)
        if not access.can_view_full(db, user, m):
            d["overview"] = None
        out.append(d)
    out.sort(key=lambda d: d["scheduled_at"] or d["created_at"], reverse=True)
    return out


@router.get("/meetings/{meeting_id}")
def meeting_detail(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = _get(db, meeting_id)
    if not access.can_view_meeting_at_all(db, user, m):
        raise HTTPException(403, "This meeting's report has not been shared with you.")
    full = access.can_view_full(db, user, m)
    d = S.meeting_brief(m)
    updates = db.scalars(select(EmployeeUpdate).where(EmployeeUpdate.meeting_id == m.id)).all()
    d["updates"] = [S.update(u) for u in updates if access.can_view_employee_section(db, user, m, u.employee_id)]
    d["participants"] = [S.participant(p) for p in m.participants]
    d["permissions"] = {
        "full": full,
        "manage": access.can_manage_meeting(user, m),
        "share": user.role == "admin" or m.organizer_user_id == user.id,
    }
    if full:
        s = dict(m.summary or {})
        s.pop("employee_reports", None)
        d["summary"] = s
        d["report_md"] = _report_for(db, user, m)
        d["transcript"] = [
            {"speaker": t.speaker, "employee_id": t.employee_id, "text": t.text, "start": t.start_seconds, "redacted": t.redacted}
            for t in m.segments
        ]
        d["consent_events"] = [
            {"kind": e.kind, "participant": e.participant, "detail": e.detail, "actor": e.actor, "at": S.iso(e.at)}
            for e in db.scalars(select(ConsentEvent).where(ConsentEvent.meeting_id == m.id).order_by(ConsentEvent.at))
        ]
    else:
        d["summary"] = None
        d["overview"] = None
    return d


@router.get("/meetings/{meeting_id}/report.md", response_class=PlainTextResponse)
def meeting_report_md(meeting_id: str, employee_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = _get(db, meeting_id)
    if employee_id:
        if not access.can_view_employee_section(db, user, m, employee_id):
            raise HTTPException(403, "That employee report has not been shared with you.")
        u = db.scalar(select(EmployeeUpdate).where(EmployeeUpdate.meeting_id == m.id, EmployeeUpdate.employee_id == employee_id))
        if not u:
            raise HTTPException(404, "No update from that employee in this meeting.")
        return f"# {m.title} - {u.employee.name}\n\n" + employee_section_md(u)
    if not access.can_view_full(db, user, m):
        raise HTTPException(403, "The full report has not been shared with you.")
    return _report_for(db, user, m) or "# Report not ready yet\n"


def _report_for(db: Session, user: User, m: Meeting) -> str:
    if m.processing_status != "done":
        return m.report_md
    return render_meeting_report(db, m, lambda eid: access.can_view_employee_section(db, user, m, eid))


# ---- create / import -------------------------------------------------------------

class MeetingCreate(BaseModel):
    title: str = Field(min_length=1)
    meeting_link: str = Field(min_length=8)
    mode: str = "notetaker"
    slot: str = "general"
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    join_at: Optional[datetime] = None
    share_full: Optional[Share] = None
    share_employee: Optional[Share] = None


@router.post("/meetings")
async def create_meeting(body: MeetingCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Send the bot now (or at join_at) - the manual join."""
    if body.mode not in ("notetaker", "standup"):
        raise HTTPException(400, "mode must be notetaker or standup")
    _require_voice(db, body.mode)
    when = body.join_at.astimezone(timezone.utc) if body.join_at and body.join_at.tzinfo else (
        body.join_at.replace(tzinfo=timezone.utc) if body.join_at else None)
    m = Meeting(
        title=body.title, meeting_link=body.meeting_link.strip(), mode=body.mode, slot=body.slot,
        team_id=body.team_id, project_id=body.project_id, organizer_user_id=user.id,
        scheduled_at=when or datetime.now(timezone.utc),
        meeting_date=(when or datetime.now(timezone.utc)).date(),
        share_full=_share(body.share_full, db, "default_share_full"),
        share_employee=_share(body.share_employee, db, "default_share_employee"),
    )
    db.add(m)
    db.commit()
    future = when if when and when > datetime.now(timezone.utc) + timedelta(seconds=60) else None
    try:
        await bots.launch(db, m, join_at=future)
    except MeetStreamError as exc:
        m.bot_status = "failed"
        m.processing_status = "skipped"
        m.stop_reason = str(exc)
        db.commit()
        raise HTTPException(502, str(exc))
    return S.meeting_brief(m)


class ImportBody(BaseModel):
    title: str = Field(min_length=1)
    transcript: str = Field(min_length=10)
    meeting_date: Optional[date] = None
    slot: str = "general"
    mode: str = "notetaker"
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    share_full: Optional[Share] = None
    share_employee: Optional[Share] = None


@router.post("/meetings/import")
async def import_transcript(body: ImportBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Analyse a pasted transcript ("Name: words" per line) without a bot."""
    turns = parse_plain_transcript(body.transcript)
    if not turns:
        raise HTTPException(400, "No 'Speaker: text' lines found in the transcript.")
    day = body.meeting_date or date.today()
    m = Meeting(
        title=body.title, mode=body.mode, slot=body.slot, team_id=body.team_id, project_id=body.project_id,
        organizer_user_id=user.id, meeting_date=day,
        scheduled_at=datetime.combine(day, time(12), tzinfo=timezone.utc),
        bot_status="imported", processing_status="fetching",
        share_full=_share(body.share_full, db, "default_share_full"),
        share_employee=_share(body.share_employee, db, "default_share_employee"),
    )
    db.add(m)
    db.commit()
    from app.services.processing import process_meeting

    asyncio.create_task(process_meeting(m.id, turns=turns))
    return S.meeting_brief(m)


# ---- controls ------------------------------------------------------------------

def _manage(db: Session, user: User, meeting_id: str) -> Meeting:
    m = _get(db, meeting_id)
    if not access.can_manage_meeting(user, m):
        raise HTTPException(403, "Only the organizer, managers and admins can control this meeting.")
    return m


@router.post("/meetings/{meeting_id}/pause")
async def pause(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = _manage(db, user, meeting_id)
    if not m.bot_id or m.bot_status not in ("in_meeting", "recording"):
        raise HTTPException(409, "The bot is not recording right now.")
    try:
        await bots.pause(db, m, user.name)
    except MeetStreamError as exc:
        raise HTTPException(502, str(exc))
    return S.meeting_brief(m)


@router.post("/meetings/{meeting_id}/resume")
async def resume(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = _manage(db, user, meeting_id)
    if not m.bot_id or not m.recording_paused:
        raise HTTPException(409, "Recording is not paused.")
    try:
        await bots.resume(db, m, user.name)
    except MeetStreamError as exc:
        raise HTTPException(502, str(exc))
    return S.meeting_brief(m)


@router.post("/meetings/{meeting_id}/remove")
async def remove(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = _manage(db, user, meeting_id)
    if not m.bot_id:
        raise HTTPException(409, "No bot was sent to this meeting.")
    try:
        await bots.remove(db, m, user.name)
    except MeetStreamError as exc:
        raise HTTPException(502, str(exc))
    return S.meeting_brief(m)


@router.post("/meetings/{meeting_id}/reprocess")
async def reprocess(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = _manage(db, user, meeting_id)
    if not m.segments and not m.bot_id:
        raise HTTPException(409, "There is no transcript to analyse.")
    m.processing_status = "waiting"
    m.processing_error = None
    m.transcript_attempts = 0
    db.commit()
    asyncio.create_task(run_processing(m.id))
    return S.meeting_brief(m)


class ShareBody(BaseModel):
    share_full: Share
    share_employee: Share


@router.put("/meetings/{meeting_id}/share")
def set_share(meeting_id: str, body: ShareBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = _get(db, meeting_id)
    if not (user.role == "admin" or m.organizer_user_id == user.id):
        raise HTTPException(403, "Only the organizer decides who can see this report.")
    m.share_full = _share(body.share_full, db, "default_share_full")
    m.share_employee = _share(body.share_employee, db, "default_share_employee")
    db.commit()
    return S.meeting_brief(m)


class MapBody(BaseModel):
    employee_id: Optional[str] = None
    remember_alias: bool = True


@router.put("/meetings/{meeting_id}/participants/{participant_id}")
def map_participant(meeting_id: str, participant_id: str, body: MapBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = _manage(db, user, meeting_id)
    p = db.get(MeetingParticipant, participant_id)
    if not p or p.meeting_id != m.id:
        raise HTTPException(404, "Participant not found.")
    p.employee_id = body.employee_id
    p.mapping = "manual" if body.employee_id else "unmatched"
    for seg in m.segments:
        if seg.speaker == p.display_name:
            seg.employee_id = body.employee_id
    if body.employee_id and body.remember_alias:
        emp = db.get(Employee, body.employee_id)
        if emp and p.display_name not in (emp.aliases or []) and p.display_name != emp.name:
            emp.aliases = [*(emp.aliases or []), p.display_name]
    db.commit()
    return S.participant(p)


@router.delete("/meetings/{meeting_id}")
async def delete_meeting(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Delete the meeting here and its recording + transcript at MeetStream."""
    m = _get(db, meeting_id)
    if not (user.role == "admin" or m.organizer_user_id == user.id):
        raise HTTPException(403, "Only the organizer or an admin can delete a meeting.")
    if m.bot_status in LIVE_STATES:
        raise HTTPException(409, "Remove the bot from the meeting first.")
    meetstream_deleted = False
    if m.bot_id and not m.media_deleted_at and meetstream.configured:
        try:
            await meetstream.delete_bot_data(m.bot_id)
            meetstream_deleted = True
        except MeetStreamError:
            pass
    db.delete(m)
    db.commit()
    return {"ok": True, "meetstream_data_deleted": meetstream_deleted}


@router.post("/meetings/{meeting_id}/delete-recording")
async def delete_recording(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Keep the report and progress records; delete the transcript and recording."""
    m = _get(db, meeting_id)
    if not (user.role == "admin" or m.organizer_user_id == user.id):
        raise HTTPException(403, "Only the organizer or an admin can delete the recording.")
    if m.bot_status in LIVE_STATES:
        raise HTTPException(409, "Remove the bot from the meeting first.")
    from app.services.retention import delete_media

    return await delete_media(db, m, actor=user.name)


@router.post("/meetings/{meeting_id}/deliver")
async def deliver_now(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """(Re)send the report by email / Slack according to its sharing."""
    m = _get(db, meeting_id)
    if not (user.role == "admin" or m.organizer_user_id == user.id):
        raise HTTPException(403, "Only the organizer or an admin can send the report.")
    if m.processing_status != "done":
        raise HTTPException(409, "The report is not ready yet.")
    from app.services import delivery

    if not (delivery.email_configured() or delivery.slack_configured()):
        raise HTTPException(400, "Neither email (SMTP_*) nor Slack (SLACK_WEBHOOK_URL) is configured in .env.")
    m.report_delivered_at = None
    db.commit()
    return await delivery.deliver(db, m)


# ---- schedules -------------------------------------------------------------------

class ScheduleBody(BaseModel):
    title: str = Field(min_length=1)
    meeting_link: str = Field(min_length=8)
    mode: str = "notetaker"
    slot: str = "general"
    recurrence: str = "weekdays"
    days_of_week: List[int] = []
    time_of_day: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: str = settings.TIMEZONE
    start_date: date
    end_date: Optional[date] = None
    duration_minutes: int = 30
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    share_full: Optional[Share] = None
    share_employee: Optional[Share] = None
    active: bool = True


def _require_voice(db: Session, mode: str) -> None:
    """Stand-ups need a host voice; there is no default, so refuse until an admin picks one."""
    from app.services import voices

    if mode == "standup" and not voices.chosen(db):
        raise HTTPException(400, voices.NO_VOICE)


def _validate_schedule(body: ScheduleBody):
    if body.recurrence not in ("once", "daily", "weekdays", "weekly"):
        raise HTTPException(400, "recurrence must be once, daily, weekdays or weekly")
    if body.recurrence == "weekly" and not body.days_of_week:
        raise HTTPException(400, "Pick at least one weekday for a weekly schedule.")
    if body.mode not in ("notetaker", "standup"):
        raise HTTPException(400, "mode must be notetaker or standup")
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(body.timezone)
    except Exception:
        raise HTTPException(400, f"Unknown timezone '{body.timezone}'.")


@router.get("/schedules")
def list_schedules(db: Session = Depends(get_db), user: User = Depends(current_user)):
    out = []
    for s in db.scalars(select(Schedule).order_by(Schedule.time_of_day)):
        if not (access.is_manager(user) or s.organizer_user_id == user.id):
            continue
        d = S.schedule(s)
        d["next"] = [S.iso(t) for t in recurrence.upcoming(s, days=14, limit=5)]
        out.append(d)
    return out


@router.get("/schedules/upcoming")
def upcoming(days: int = 7, db: Session = Depends(get_db), user: User = Depends(current_user)):
    out = []
    for s in db.scalars(select(Schedule).where(Schedule.active.is_(True))):
        if not (access.is_manager(user) or s.organizer_user_id == user.id):
            continue
        for t in recurrence.upcoming(s, days=days, limit=50):
            out.append({"schedule_id": s.id, "title": s.title, "mode": s.mode, "slot": s.slot, "at": S.iso(t)})
    return sorted(out, key=lambda x: x["at"])


def _apply_schedule(db: Session, s: Schedule, body: ScheduleBody):
    data = body.model_dump(exclude={"share_full", "share_employee"})
    for k, v in data.items():
        setattr(s, k, v)
    s.share_full = _share(body.share_full, db, "default_share_full")
    s.share_employee = _share(body.share_employee, db, "default_share_employee")


@router.post("/schedules")
def create_schedule(body: ScheduleBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _validate_schedule(body)
    _require_voice(db, body.mode)
    s = Schedule(organizer_user_id=user.id, time_of_day=body.time_of_day, start_date=body.start_date, title=body.title,
                 meeting_link=body.meeting_link)
    _apply_schedule(db, s, body)
    db.add(s)
    db.commit()
    return S.schedule(s)


@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: str, body: ScheduleBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _validate_schedule(body)
    _require_voice(db, body.mode)
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(404, "Schedule not found.")
    if not (access.is_manager(user) or s.organizer_user_id == user.id):
        raise HTTPException(403, "Only the organizer or a manager can edit this schedule.")
    _apply_schedule(db, s, body)
    db.commit()
    return S.schedule(s)


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(404, "Schedule not found.")
    if not (access.is_manager(user) or s.organizer_user_id == user.id):
        raise HTTPException(403, "Only the organizer or a manager can delete this schedule.")
    # Cancel bots already booked for future occurrences.
    for m in db.scalars(select(Meeting).where(Meeting.schedule_id == s.id, Meeting.bot_status == "scheduled")):
        try:
            await bots.remove(db, m, user.name)
        except MeetStreamError:
            pass
    db.delete(s)
    db.commit()
    return {"ok": True}
