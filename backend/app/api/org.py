"""Teams, projects, employees, users, settings and integrations."""
from __future__ import annotations

from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import access
from app.api import serializers as S
from app.auth import current_user, hash_password, require_admin, require_manager
from app.config import settings
from app.db import get_db
from app.models import Employee, EmployeeProject, MeetingParticipant, Project, Team, User
from app.services import integrations
from app.services.app_settings import DEFAULTS, SECRET_KEYS, all_settings, set_settings
from app.services.extraction import provider
from app.services.meetstream import meetstream

router = APIRouter(prefix="/api", tags=["org"])


# ---- teams -------------------------------------------------------------------

class TeamBody(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    lead_employee_id: Optional[str] = None


@router.get("/teams")
def list_teams(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [S.team(t) for t in db.scalars(select(Team).order_by(Team.name))]


@router.post("/teams")
def create_team(body: TeamBody, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    t = Team(**body.model_dump())
    db.add(t)
    db.commit()
    return S.team(t)


@router.put("/teams/{team_id}")
def update_team(team_id: str, body: TeamBody, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    t = db.get(Team, team_id) or _404("Team")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    db.commit()
    return S.team(t)


@router.delete("/teams/{team_id}")
def delete_team(team_id: str, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    db.delete(db.get(Team, team_id) or _404("Team"))
    db.commit()
    return {"ok": True}


# ---- projects ----------------------------------------------------------------

class ProjectBody(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    team_id: Optional[str] = None
    status: str = "active"
    keywords: List[str] = []
    member_ids: Optional[List[str]] = None


@router.get("/projects")
def list_projects(db: Session = Depends(get_db), _: User = Depends(current_user)):
    out = []
    for p in db.scalars(select(Project).order_by(Project.name)):
        d = S.project(p)
        d["member_ids"] = list(db.scalars(select(EmployeeProject.employee_id).where(EmployeeProject.project_id == p.id)))
        out.append(d)
    return out


def _save_members(db: Session, project_id: str, member_ids: Optional[List[str]]):
    if member_ids is None:
        return
    for row in db.scalars(select(EmployeeProject).where(EmployeeProject.project_id == project_id)):
        db.delete(row)
    db.flush()
    for eid in set(member_ids):
        db.add(EmployeeProject(employee_id=eid, project_id=project_id))


@router.post("/projects")
def create_project(body: ProjectBody, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    data = body.model_dump(exclude={"member_ids"})
    p = Project(**data)
    db.add(p)
    db.flush()
    _save_members(db, p.id, body.member_ids)
    db.commit()
    return S.project(p)


@router.put("/projects/{project_id}")
def update_project(project_id: str, body: ProjectBody, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    p = db.get(Project, project_id) or _404("Project")
    for k, v in body.model_dump(exclude={"member_ids"}).items():
        setattr(p, k, v)
    _save_members(db, p.id, body.member_ids)
    db.commit()
    return S.project(p)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    db.delete(db.get(Project, project_id) or _404("Project"))
    db.commit()
    return {"ok": True}


# ---- employees ---------------------------------------------------------------

class EmployeeBody(BaseModel):
    name: str = Field(min_length=1)
    email: Optional[str] = None
    title: str = ""
    team_id: Optional[str] = None
    aliases: List[str] = []
    active: bool = True
    project_ids: Optional[List[str]] = None
    trello_member_id: Optional[str] = None


@router.get("/employees")
def list_employees(db: Session = Depends(get_db), user: User = Depends(current_user)):
    visible = access.visible_employee_ids(db, user)
    q = select(Employee).order_by(Employee.name)
    rows = [e for e in db.scalars(q) if visible is None or e.id in visible]
    out = []
    for e in rows:
        d = S.employee(e)
        d["project_ids"] = list(db.scalars(select(EmployeeProject.project_id).where(EmployeeProject.employee_id == e.id)))
        out.append(d)
    return out


@router.get("/employees/directory")
def employee_directory(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Names only - used for share pickers and participant mapping."""
    return [{"id": e.id, "name": e.name} for e in db.scalars(select(Employee).where(Employee.active.is_(True)).order_by(Employee.name))]


def _save_projects(db: Session, emp_id: str, project_ids: Optional[List[str]]):
    if project_ids is None:
        return
    for row in db.scalars(select(EmployeeProject).where(EmployeeProject.employee_id == emp_id)):
        db.delete(row)
    db.flush()
    for pid in set(project_ids):
        db.add(EmployeeProject(employee_id=emp_id, project_id=pid))


@router.post("/employees")
def create_employee(body: EmployeeBody, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    e = Employee(**body.model_dump(exclude={"project_ids"}))
    db.add(e)
    db.flush()
    _save_projects(db, e.id, body.project_ids)
    db.commit()
    return S.employee(e)


@router.put("/employees/{employee_id}")
def update_employee(employee_id: str, body: EmployeeBody, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    e = db.get(Employee, employee_id) or _404("Employee")
    skip = {"project_ids"} | ({"trello_member_id"} - body.model_fields_set)  # only change it when sent
    for k, v in body.model_dump(exclude=skip).items():
        setattr(e, k, v)
    _save_projects(db, e.id, body.project_ids)
    db.commit()
    return S.employee(e)


@router.delete("/employees/{employee_id}")
def deactivate_employee(employee_id: str, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    e = db.get(Employee, employee_id) or _404("Employee")
    e.active = False
    db.commit()
    return {"ok": True}


@router.get("/participants/unmatched")
def unmatched_names(db: Session = Depends(get_db), _: User = Depends(require_manager)):
    """Meeting display names not yet linked to anyone - to map in bulk."""
    rows = db.execute(
        select(MeetingParticipant.display_name).where(
            MeetingParticipant.employee_id.is_(None), MeetingParticipant.is_bot.is_(False)
        ).distinct()
    ).scalars()
    return sorted(set(rows))


# ---- users -------------------------------------------------------------------

class UserBody(BaseModel):
    email: str
    name: str
    role: str = "employee"
    password: Optional[str] = None
    employee_id: Optional[str] = None


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [S.user(u) for u in db.scalars(select(User).order_by(User.name))]


@router.post("/users")
def create_user(body: UserBody, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if body.role not in ("admin", "manager", "employee"):
        raise HTTPException(400, "Role must be admin, manager or employee.")
    if not body.password or len(body.password) < 8:
        raise HTTPException(400, "Give the user a password of at least 8 characters.")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "A user with that email already exists.")
    u = User(email=body.email.lower(), name=body.name, role=body.role,
             password_hash=hash_password(body.password), employee_id=body.employee_id)
    db.add(u)
    db.commit()
    return S.user(u)


@router.put("/users/{user_id}")
def update_user(user_id: str, body: UserBody, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.get(User, user_id) or _404("User")
    if body.role not in ("admin", "manager", "employee"):
        raise HTTPException(400, "Role must be admin, manager or employee.")
    if u.id == admin.id and body.role != "admin":
        raise HTTPException(400, "You cannot remove your own admin role.")
    u.email, u.name, u.role, u.employee_id = body.email.lower(), body.name, body.role, body.employee_id
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(400, "Passwords need at least 8 characters.")
        u.password_hash = hash_password(body.password)
    db.commit()
    return S.user(u)


@router.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(400, "You cannot delete yourself.")
    db.delete(db.get(User, user_id) or _404("User"))
    db.commit()
    return {"ok": True}


# ---- settings & integrations --------------------------------------------------

class DeliveryTest(BaseModel):
    channel: str  # email | slack


@router.post("/settings/delivery-test")
async def delivery_test(body: DeliveryTest, admin: User = Depends(require_admin)):
    from app.services.delivery import send_test

    try:
        return {"message": await send_test(body.channel, admin.email)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(current_user)):
    values = {k: v for k, v in all_settings(db).items() if k not in SECRET_KEYS}
    return {
        "values": values,
        "environment": {
            "meetstream_configured": meetstream.configured,
            "analysis_provider": provider(),
            "analysis_configured": bool(settings.GEMINI_API_KEY if provider() == "gemini" else settings.ANTHROPIC_API_KEY),
            "analysis_model": settings.GEMINI_MODEL if provider() == "gemini" else settings.ANALYSIS_MODEL,
            "public_url": settings.public_url,
            "tunnel": __import__("app.services.tunnel", fromlist=["tunnel"]).tunnel.describe(),
            "email_configured": bool(settings.SMTP_HOST and settings.SMTP_FROM),
            "slack_configured": bool(settings.SLACK_WEBHOOK_URL),
            "transcript_provider": settings.TRANSCRIPT_PROVIDER,
            "timezone": settings.TIMEZONE,
            "mia_model": f"{settings.MIA_MODEL_PROVIDER}/{settings.MIA_MODEL}",
        },
    }


@router.put("/settings")
def put_settings(values: dict, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    clean = {k: v for k, v in values.items() if k in DEFAULTS and k not in SECRET_KEYS}
    set_settings(db, clean)
    return {"ok": True}


@router.get("/integrations")
def list_integrations(_: User = Depends(current_user)):
    return integrations.status_list()


@router.post("/integrations/{name}/check")
async def check_integration(name: str, _: User = Depends(require_manager)):
    from app.services.integrations.base import IntegrationError

    try:
        result = await integrations.get_provider(name).check_connection()
    except IntegrationError as exc:
        raise HTTPException(400, str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Could not reach the service ({exc.__class__.__name__}).")
    target, url = result if isinstance(result, tuple) else (result, None)
    return {"message": f"Connected. New tasks go to {target}.", "url": url}


@router.post("/integrations/sync")
async def sync_integrations(db: Session = Depends(get_db), _: User = Depends(require_manager)):
    return await integrations.sync_all(db)


def _404(what: str):
    raise HTTPException(404, f"{what} not found.")
