"""Who may see what.

* admin: everything (the person running this install).
* manager: all employee records; meeting reports as shared by the organizer.
* team lead (an employee who leads a team): records of their team members.
* employee: their own records always; meeting reports only when shared.

Report sharing is chosen per meeting by the organizer, separately for the
full meeting report (``share_full``) and the per-employee sections
(``share_employee``). Audiences: organizer, participants, managers, selected.
"""
from __future__ import annotations

from typing import Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Employee, Meeting, Team, User

AUDIENCES = ("organizer", "participants", "managers", "selected")


def led_team_ids(db: Session, user: User) -> Set[str]:
    """Teams this user leads. Cached on the (request-scoped) user object,
    since list endpoints run access checks once per row."""
    if not user.employee_id:
        return set()
    cached = user.__dict__.get("_led_team_ids")
    if cached is None:
        cached = set(db.scalars(select(Team.id).where(Team.lead_employee_id == user.employee_id)))
        user.__dict__["_led_team_ids"] = cached
    return cached


def is_manager(user: User) -> bool:
    return user.role in ("admin", "manager")


def visible_employee_ids(db: Session, user: User) -> Optional[Set[str]]:
    """None means 'all'."""
    if is_manager(user):
        return None
    ids: Set[str] = set()
    if user.employee_id:
        ids.add(user.employee_id)
    teams = led_team_ids(db, user)
    if teams:
        ids |= set(db.scalars(select(Employee.id).where(Employee.team_id.in_(teams))))
    return ids


def can_see_employee(db: Session, user: User, employee_id: str) -> bool:
    ids = visible_employee_ids(db, user)
    return ids is None or employee_id in ids


def _participant_employee_ids(meeting: Meeting) -> Set[str]:
    return {p.employee_id for p in meeting.participants if p.employee_id}


def _matches(db: Session, user: User, meeting: Meeting, share: dict) -> bool:
    audience = (share or {}).get("audience") or "participants"
    if audience == "organizer":
        return False  # organizer/admin handled by caller
    if audience == "selected":
        return user.id in ((share or {}).get("user_ids") or [])
    if audience == "managers":
        if is_manager(user):
            return True
        teams = led_team_ids(db, user)
        return bool(teams) and (meeting.team_id is None or meeting.team_id in teams)
    if audience == "participants":
        if user.employee_id and user.employee_id in _participant_employee_ids(meeting):
            return True
        return False
    return False


def can_manage_meeting(user: User, meeting: Meeting) -> bool:
    return user.role in ("admin", "manager") or meeting.organizer_user_id == user.id


def can_view_full(db: Session, user: User, meeting: Meeting) -> bool:
    if user.role == "admin" or meeting.organizer_user_id == user.id:
        return True
    return _matches(db, user, meeting, meeting.share_full)


def can_view_employee_section(db: Session, user: User, meeting: Meeting, employee_id: str) -> bool:
    """Per-employee sections are shared separately from the full report."""
    if user.employee_id == employee_id:
        return True
    if user.role == "admin" or meeting.organizer_user_id == user.id:
        return True
    return _matches(db, user, meeting, meeting.share_employee)


def can_view_meeting_at_all(db: Session, user: User, meeting: Meeting) -> bool:
    if can_view_full(db, user, meeting) or can_manage_meeting(user, meeting):
        return True
    if user.employee_id and user.employee_id in _participant_employee_ids(meeting):
        return True  # can at least see their own section
    return _matches(db, user, meeting, meeting.share_employee)
