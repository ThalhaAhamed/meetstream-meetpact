"""Dashboards, employee progress, work items, blockers, reviews and reports."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import access
from app.api import serializers as S
from app.auth import current_user
from app.db import get_db
from app.models import (
    Blocker,
    Employee,
    EmployeeProject,
    EmployeeUpdate,
    Meeting,
    Project,
    Team,
    User,
    WorkItem,
    WorkItemEvent,
)
from app.services import integrations, reports, tracker
from app.services.integrations.base import IntegrationError

router = APIRouter(prefix="/api", tags=["progress"])
OPEN = ("planned", "in_progress", "blocked")


def _visible(db: Session, user: User) -> Optional[set]:
    return access.visible_employee_ids(db, user)


def _check_employee(db: Session, user: User, employee_id: str) -> Employee:
    e = db.get(Employee, employee_id)
    if not e:
        raise HTTPException(404, "Employee not found.")
    if not access.can_see_employee(db, user, employee_id):
        raise HTTPException(403, "You can only see your own records and your team's.")
    return e


# ---- dashboards ------------------------------------------------------------------

@router.get("/dashboard")
def dashboard(team_id: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Team overview for managers and team leads (scoped to who they may see)."""
    visible = _visible(db, user)
    emp_q = select(Employee).where(Employee.active.is_(True))
    if team_id:
        emp_q = emp_q.where(Employee.team_id == team_id)
    employees = [e for e in db.scalars(emp_q.order_by(Employee.name)) if visible is None or e.id in visible]
    ids = [e.id for e in employees]
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_t0 = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)

    items = db.scalars(select(WorkItem).where(WorkItem.employee_id.in_(ids))).all()
    blockers = db.scalars(select(Blocker).where(Blocker.employee_id.in_(ids), Blocker.status == "open").order_by(Blocker.created_at.desc())).all()
    rows = []
    for e in employees:
        mine = [w for w in items if w.employee_id == e.id]
        last = db.scalar(select(EmployeeUpdate).where(EmployeeUpdate.employee_id == e.id).order_by(EmployeeUpdate.created_at.desc()))
        rows.append({
            **S.employee(e),
            "open": sum(w.status in OPEN for w in mine),
            "in_progress": sum(w.status == "in_progress" for w in mine),
            "blocked": sum(w.status == "blocked" for w in mine),
            "overdue": sum(bool(w.due_date and w.due_date < today and w.status in OPEN) for w in mine),
            "carried_over": sum(w.carry_count >= 2 and w.status in OPEN for w in mine),
            "completed_week": sum(bool(w.completed_at and _aware(w.completed_at) >= week_t0) for w in mine),
            "open_blockers": sum(b.employee_id == e.id for b in blockers),
            "last_update": S.update(last) if last else None,
        })

    meetings = [m for m in db.scalars(select(Meeting).order_by(Meeting.created_at.desc()).limit(40))
                if access.can_view_meeting_at_all(db, user, m)][:8]
    projects = project_progress(db, ids)
    totals = {
        "employees": len(employees),
        "open": sum(r["open"] for r in rows),
        "overdue": sum(r["overdue"] for r in rows),
        "blockers": len(blockers),
        "completed_week": sum(r["completed_week"] for r in rows),
        "meetings_week": sum(
            1 for m in db.scalars(
                select(Meeting).options(selectinload(Meeting.participants)).where(Meeting.meeting_date >= week_start)
            )
            if (not team_id or m.team_id == team_id) and access.can_view_meeting_at_all(db, user, m)
        ),
        "unreviewed": db.scalar(select(func.count(EmployeeUpdate.id)).where(EmployeeUpdate.employee_id.in_(ids), EmployeeUpdate.review_status == "unreviewed")) or 0,
    }
    # Completion trend: items completed per day, last 14 days.
    trend = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        trend.append({"date": d.isoformat(), "completed": sum(1 for w in items if w.completed_at and _aware(w.completed_at).date() == d),
                      "created": sum(1 for w in items if _aware(w.created_at).date() == d)})
    # What a manager should look at first, most urgent first.
    attention = []
    for w in sorted((w for w in items if w.status in OPEN and w.due_date and w.due_date < today), key=lambda w: w.due_date):
        attention.append({"kind": "overdue", "title": w.title, "employee_id": w.employee_id,
                          "employee_name": w.employee.name if w.employee else None, "item_id": w.id,
                          "detail": f"due {w.due_date.isoformat()}", "days": (today - w.due_date).days})
    for b in sorted(blockers, key=lambda b: _aware(b.created_at)):
        age = (datetime.now(timezone.utc) - _aware(b.created_at)).days
        attention.append({"kind": "blocker", "title": b.description, "employee_id": b.employee_id,
                          "employee_name": b.employee.name if b.employee else None, "item_id": None,
                          "detail": f"open {age} day{'s' if age != 1 else ''}" + (f", raised {b.mention_count}×" if b.mention_count > 1 else ""),
                          "days": age})
    for w in sorted((w for w in items if w.status in OPEN and w.carry_count >= 2), key=lambda w: -w.carry_count):
        attention.append({"kind": "carried", "title": w.title, "employee_id": w.employee_id,
                          "employee_name": w.employee.name if w.employee else None, "item_id": w.id,
                          "detail": f"carried over {w.carry_count} meetings", "days": w.carry_count})
    return {
        "totals": totals,
        "attention": attention[:8],
        "employees": rows,
        "blockers": [S.blocker(b) for b in blockers[:20]],
        "recent_meetings": [S.meeting_brief(m) for m in meetings],
        "projects": projects,
        "trend": trend,
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def project_progress(db: Session, employee_ids: Optional[List[str]] = None) -> List[dict]:
    out = []
    for p in db.scalars(select(Project).order_by(Project.name)):
        q = select(WorkItem).where(WorkItem.project_id == p.id)
        if employee_ids is not None:
            q = q.where(WorkItem.employee_id.in_(employee_ids))
        items = db.scalars(q).all()
        total = len([w for w in items if w.status != "dropped"])
        done = len([w for w in items if w.status == "completed"])
        out.append({
            **S.project(p),
            "total": total, "completed": done,
            "in_progress": len([w for w in items if w.status == "in_progress"]),
            "blocked": len([w for w in items if w.status == "blocked"]),
            "percent": round(100 * done / total) if total else 0,
            "members": len(db.scalars(select(EmployeeProject).where(EmployeeProject.project_id == p.id)).all()),
            "open_blockers": db.scalar(select(func.count(Blocker.id)).where(Blocker.project_id == p.id, Blocker.status == "open")) or 0,
        })
    return out


@router.get("/projects/progress")
def projects_progress(db: Session = Depends(get_db), user: User = Depends(current_user)):
    visible = _visible(db, user)
    return project_progress(db, None if visible is None else list(visible))


@router.get("/projects/{project_id}/items")
def project_items(project_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    visible = _visible(db, user)
    items = db.scalars(select(WorkItem).where(WorkItem.project_id == project_id).order_by(WorkItem.updated_at.desc())).all()
    return [S.work_item(w) for w in items if visible is None or w.employee_id in visible]


@router.get("/me/dashboard")
def my_dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not user.employee_id:
        return {"employee": None}
    return employee_profile(user.employee_id, db, user)


@router.get("/employees/{employee_id}/profile")
def employee_profile(employee_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = _check_employee(db, user, employee_id)
    items = db.scalars(select(WorkItem).where(WorkItem.employee_id == e.id).order_by(WorkItem.updated_at.desc())).all()
    updates = db.scalars(select(EmployeeUpdate).where(EmployeeUpdate.employee_id == e.id).order_by(EmployeeUpdate.created_at.desc()).limit(60)).all()
    blockers = db.scalars(select(Blocker).where(Blocker.employee_id == e.id).order_by(Blocker.created_at.desc())).all()
    meeting_ids = {u.meeting_id for u in updates}
    meetings = []
    for m in db.scalars(select(Meeting).where(Meeting.id.in_(meeting_ids)).order_by(Meeting.created_at.desc())):
        d = S.meeting_brief(m)
        d["can_view_full"] = access.can_view_full(db, user, m)
        if not d["can_view_full"]:
            d["overview"] = None
        meetings.append(d)
    return {
        "employee": S.employee(e),
        "work_items": [S.work_item(w) for w in items],
        "updates": [S.update(u) for u in updates],
        "blockers": [S.blocker(b) for b in blockers],
        "meetings": meetings,
        "stats": {
            "open": sum(w.status in OPEN for w in items),
            "completed": sum(w.status == "completed" for w in items),
            "overdue": sum(bool(w.due_date and w.due_date < date.today() and w.status in OPEN) for w in items),
            "open_blockers": sum(b.status == "open" for b in blockers),
            "unreviewed": sum(u.review_status == "unreviewed" for u in updates),
        },
        "can_edit": user.employee_id == e.id or access.is_manager(user) or bool(access.led_team_ids(db, user) and e.team_id in access.led_team_ids(db, user)),
    }


# ---- work items -----------------------------------------------------------------

def _can_edit_item(db: Session, user: User, item: WorkItem) -> bool:
    if access.is_manager(user):
        return True
    if item.employee_id and item.employee_id == user.employee_id:
        return True
    return bool(item.employee_id and access.can_see_employee(db, user, item.employee_id) and access.led_team_ids(db, user))


@router.get("/work-items")
def list_items(
    status: Optional[str] = None,
    employee_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    visible = _visible(db, user)
    q = select(WorkItem).order_by(WorkItem.updated_at.desc())
    if status == "open":
        q = q.where(WorkItem.status.in_(OPEN))
    elif status:
        q = q.where(WorkItem.status == status)
    if employee_id:
        q = q.where(WorkItem.employee_id == employee_id)
    if project_id:
        q = q.where(WorkItem.project_id == project_id)
    return [S.work_item(w) for w in db.scalars(q.limit(500))
            if visible is None or w.employee_id in visible or (w.employee_id is None and access.is_manager(user))]


class ItemBody(BaseModel):
    title: Optional[str] = None
    details: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[date] = None
    clear_due: bool = False
    employee_id: Optional[str] = None
    project_id: Optional[str] = None
    note: str = ""


@router.post("/work-items")
def create_item(body: ItemBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    emp_id = body.employee_id or user.employee_id
    if not body.title:
        raise HTTPException(400, "Give the work item a title.")
    if emp_id and not access.can_see_employee(db, user, emp_id):
        raise HTTPException(403, "You cannot add work for that person.")
    item = tracker.create_item(db, employee_id=emp_id, title=body.title, status=body.status or "planned", meeting=None,
                               due=body.due_date, project_id=body.project_id, source="manual", actor=user.name)
    db.commit()
    return S.work_item(item)


@router.get("/work-items/{item_id}")
def get_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(WorkItem, item_id)
    allowed = item and (
        access.can_see_employee(db, user, item.employee_id) if item.employee_id else access.is_manager(user)
    )
    if not allowed:
        raise HTTPException(404, "Work item not found.")
    return {**S.work_item(item), "history": reports.item_history(db, item.id)}


@router.patch("/work-items/{item_id}")
def edit_item(item_id: str, body: ItemBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Correct an AI record (or update a manual one). Every change is logged."""
    item = db.get(WorkItem, item_id)
    if not item:
        raise HTTPException(404, "Work item not found.")
    if not _can_edit_item(db, user, item):
        raise HTTPException(403, "You can only correct your own records (or your team's as a lead).")
    note = body.note or "Corrected by hand"
    if body.title and body.title != item.title:
        db.add(WorkItemEvent(work_item_id=item.id, kind="corrected", note=f"Title: '{item.title}' → '{body.title}'", actor=user.name))
        item.title = body.title
    if body.details is not None:
        item.details = body.details
    if body.status and body.status != item.status:
        if body.status not in ("planned", "in_progress", "blocked", "completed", "dropped"):
            raise HTTPException(400, "Unknown status.")
        tracker.set_status(db, item, body.status, None, note, actor=user.name)
    if body.clear_due or (body.due_date and body.due_date != item.due_date):
        new = None if body.clear_due else body.due_date
        db.add(WorkItemEvent(work_item_id=item.id, kind="due_changed", note=f"Deadline {item.due_date or 'none'} → {new or 'none'}", actor=user.name))
        item.due_date = new
    if body.employee_id is not None and body.employee_id != item.employee_id and access.is_manager(user):
        db.add(WorkItemEvent(work_item_id=item.id, kind="corrected", note="Reassigned", actor=user.name))
        item.employee_id = body.employee_id or None
    if body.project_id is not None:
        item.project_id = body.project_id or None
    db.commit()
    return S.work_item(item)


@router.delete("/work-items/{item_id}")
def delete_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(WorkItem, item_id)
    if not item:
        raise HTTPException(404, "Work item not found.")
    if not _can_edit_item(db, user, item):
        raise HTTPException(403, "Not allowed.")
    db.delete(item)
    db.commit()
    return {"ok": True}


class PushBody(BaseModel):
    provider: str


@router.post("/work-items/{item_id}/push")
async def push_item(item_id: str, body: PushBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(WorkItem, item_id)
    if not item or not _can_edit_item(db, user, item):
        raise HTTPException(404, "Work item not found.")
    try:
        await integrations.push_item(db, item, body.provider, actor=user.name)
    except IntegrationError as exc:
        raise HTTPException(400, str(exc))
    return S.work_item(item)


@router.post("/work-items/{item_id}/sync")
async def sync_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(WorkItem, item_id)
    if not item or not _can_edit_item(db, user, item):
        raise HTTPException(404, "Work item not found.")
    try:
        await integrations.sync_item(db, item)
    except IntegrationError as exc:
        raise HTTPException(400, str(exc))
    return S.work_item(item)


# ---- blockers --------------------------------------------------------------------

@router.get("/blockers")
def list_blockers(status: str = "open", db: Session = Depends(get_db), user: User = Depends(current_user)):
    visible = _visible(db, user)
    q = select(Blocker).order_by(Blocker.created_at.desc())
    if status != "all":
        q = q.where(Blocker.status == status)
    return [S.blocker(b) for b in db.scalars(q) if visible is None or b.employee_id in visible]


class BlockerBody(BaseModel):
    status: Optional[str] = None
    description: Optional[str] = None


@router.patch("/blockers/{blocker_id}")
def edit_blocker(blocker_id: str, body: BlockerBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = db.get(Blocker, blocker_id)
    if not b or not (access.is_manager(user) or b.employee_id == user.employee_id or
                     (b.employee_id and access.can_see_employee(db, user, b.employee_id))):
        raise HTTPException(404, "Blocker not found.")
    if body.description:
        b.description = body.description
    if body.status in ("open", "resolved"):
        b.status = body.status
        b.resolved_at = datetime.now(timezone.utc) if body.status == "resolved" else None
    db.commit()
    return S.blocker(b)


# ---- updates & review --------------------------------------------------------------

class ReviewBody(BaseModel):
    review_status: str  # confirmed | corrected
    employee_note: str = ""
    completed: Optional[List[str]] = None
    in_progress: Optional[List[str]] = None
    planned: Optional[List[str]] = None
    pending: Optional[List[str]] = None
    blockers: Optional[List[str]] = None
    summary: Optional[str] = None


@router.patch("/updates/{update_id}")
def review_update(update_id: str, body: ReviewBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The employee confirms or corrects what the AI recorded for them."""
    u = db.get(EmployeeUpdate, update_id)
    if not u:
        raise HTTPException(404, "Update not found.")
    if not (u.employee_id == user.employee_id or access.is_manager(user)):
        raise HTTPException(403, "Only the employee (or a manager) can review this update.")
    if body.review_status not in ("confirmed", "corrected", "unreviewed"):
        raise HTTPException(400, "review_status must be confirmed or corrected.")
    for field in ("completed", "in_progress", "planned", "pending", "blockers", "summary"):
        val = getattr(body, field)
        if val is not None:
            setattr(u, field, val)
    u.review_status = body.review_status
    u.employee_note = body.employee_note
    u.reviewed_at = datetime.now(timezone.utc)
    m = db.get(Meeting, u.meeting_id)
    if m and m.processing_status == "done":
        m.report_md = reports.render_meeting_report(db, m)
    db.commit()
    return S.update(u)


@router.get("/updates")
def list_updates(employee_id: Optional[str] = None, day: Optional[date] = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    visible = _visible(db, user)
    q = select(EmployeeUpdate).order_by(EmployeeUpdate.created_at.desc()).limit(300)
    if employee_id:
        q = q.where(EmployeeUpdate.employee_id == employee_id)
    if day:
        q = q.where(EmployeeUpdate.meeting_date == day)
    return [S.update(u) for u in db.scalars(q) if visible is None or u.employee_id in visible]


# ---- reports -----------------------------------------------------------------------

@router.get("/reports/period")
def period(
    period: str = "weekly",
    anchor: Optional[date] = None,
    team_id: Optional[str] = None,
    project_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    visible = _visible(db, user)
    ids = None if visible is None else list(visible)
    if employee_id:
        _check_employee(db, user, employee_id)
        ids = [employee_id]
    try:
        return reports.period_report(db, period, anchor or date.today(), employee_ids=ids, project_id=project_id, team_id=team_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
