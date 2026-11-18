"""Model -> JSON dicts. Timestamps always leave with an explicit UTC offset."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from app.models import (
    Blocker,
    Employee,
    EmployeeUpdate,
    Meeting,
    MeetingParticipant,
    Project,
    Schedule,
    Team,
    User,
    WorkItem,
)


def iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def user(u: User) -> Dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "employee_id": u.employee_id}


def team(t: Team) -> Dict:
    return {"id": t.id, "name": t.name, "description": t.description, "lead_employee_id": t.lead_employee_id}


def project(p: Project) -> Dict:
    return {"id": p.id, "name": p.name, "description": p.description, "team_id": p.team_id,
            "status": p.status, "keywords": p.keywords or []}


def employee(e: Employee) -> Dict:
    return {"id": e.id, "name": e.name, "email": e.email, "title": e.title, "team_id": e.team_id,
            "team_name": e.team.name if e.team else None, "aliases": e.aliases or [], "active": e.active}


def work_item(w: WorkItem) -> Dict:
    return {
        "id": w.id, "title": w.title, "details": w.details, "kind": w.kind, "status": w.status,
        "due_date": iso(w.due_date), "source": w.source, "carry_count": w.carry_count,
        "employee_id": w.employee_id, "employee_name": w.employee.name if w.employee else None,
        "project_id": w.project_id, "project_name": w.project.name if w.project else None,
        "created_meeting_id": w.created_meeting_id, "last_meeting_id": w.last_meeting_id,
        "completed_at": iso(w.completed_at), "created_at": iso(w.created_at), "updated_at": iso(w.updated_at),
        "external": {"provider": w.external_provider, "id": w.external_id, "url": w.external_url,
                     "status": w.external_status, "synced_at": iso(w.external_synced_at)} if w.external_id else None,
        "overdue": bool(w.due_date and w.status in ("planned", "in_progress", "blocked") and w.due_date < date.today()),
    }


def blocker(b: Blocker) -> Dict:
    return {"id": b.id, "description": b.description, "status": b.status, "employee_id": b.employee_id,
            "employee_name": b.employee.name if b.employee else None, "project_id": b.project_id,
            "raised_meeting_id": b.raised_meeting_id, "resolved_meeting_id": b.resolved_meeting_id,
            "mention_count": b.mention_count, "created_at": iso(b.created_at), "resolved_at": iso(b.resolved_at)}


def update(u: EmployeeUpdate) -> Dict:
    return {
        "id": u.id, "meeting_id": u.meeting_id, "meeting_title": u.meeting.title if u.meeting else None,
        "employee_id": u.employee_id, "employee_name": u.employee.name if u.employee else None,
        "slot": u.slot, "meeting_date": iso(u.meeting_date), "summary": u.summary,
        "completed": u.completed, "in_progress": u.in_progress, "planned": u.planned, "pending": u.pending,
        "blockers": u.blockers, "commitments": u.commitments, "review_status": u.review_status,
        "employee_note": u.employee_note, "reviewed_at": iso(u.reviewed_at), "created_at": iso(u.created_at),
    }


def participant(p: MeetingParticipant) -> Dict:
    return {"id": p.id, "display_name": p.display_name, "employee_id": p.employee_id,
            "employee_name": p.employee.name if p.employee else None, "mapping": p.mapping,
            "joined_late": p.joined_late, "notice_sent": p.notice_sent, "opted_out": p.opted_out,
            "is_bot": p.is_bot, "first_seen_at": iso(p.first_seen_at)}


def meeting_brief(m: Meeting) -> Dict:
    return {
        "id": m.id, "title": m.title, "mode": m.mode, "slot": m.slot, "meeting_link": m.meeting_link,
        "schedule_id": m.schedule_id, "team_id": m.team_id, "project_id": m.project_id,
        "organizer_user_id": m.organizer_user_id,
        "scheduled_at": iso(m.scheduled_at), "meeting_date": iso(m.meeting_date),
        "started_at": iso(m.started_at), "ended_at": iso(m.ended_at), "created_at": iso(m.created_at),
        "bot_id": m.bot_id, "bot_status": m.bot_status, "stop_reason": m.stop_reason,
        "processing_status": m.processing_status, "processing_error": m.processing_error,
        "recording_paused": m.recording_paused, "consent_notice_sent": m.consent_notice_sent,
        "overview": (m.summary or {}).get("overview"),
        "participant_count": len([p for p in m.participants if not p.is_bot]),
        "share_full": m.share_full or {}, "share_employee": m.share_employee or {},
        "report_delivered_at": iso(m.report_delivered_at), "media_deleted_at": iso(m.media_deleted_at),
    }


def schedule(s: Schedule) -> Dict:
    return {
        "id": s.id, "title": s.title, "meeting_link": s.meeting_link, "mode": s.mode, "slot": s.slot,
        "recurrence": s.recurrence, "days_of_week": s.days_of_week or [], "time_of_day": s.time_of_day,
        "timezone": s.timezone, "start_date": iso(s.start_date), "end_date": iso(s.end_date),
        "duration_minutes": s.duration_minutes, "team_id": s.team_id, "project_id": s.project_id,
        "organizer_user_id": s.organizer_user_id, "share_full": s.share_full or {},
        "share_employee": s.share_employee or {}, "active": s.active, "created_at": iso(s.created_at),
    }
