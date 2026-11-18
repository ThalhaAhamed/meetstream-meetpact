"""Task boards per team: MeetPact's own board, or the team's Trello board."""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import access
from app.auth import current_user, require_admin, require_manager
from app.config import settings
from app.db import get_db
from app.models import Employee, Team, User, WorkItem
from app.services import trello_board as tb
from app.services.app_settings import set_settings

router = APIRouter(prefix="/api", tags=["boards"])


def _err(exc: tb.TrelloError):
    raise HTTPException(400, str(exc))


# ---- Trello connection -------------------------------------------------------

@router.get("/trello")
async def trello_status(db: Session = Depends(get_db), _: User = Depends(require_manager)):
    key, token = tb.credentials(db)
    out = {"connected": False, "account": None, "has_key": bool(key), "from_env": bool(settings.TRELLO_TOKEN),
           "authorize_url": tb.authorize_url(key) if key else None, "error": None}
    if key and token:
        try:
            out["account"] = await tb.whoami(db)
            out["connected"] = True
        except tb.TrelloError as exc:
            out["error"] = str(exc)
    return out


class TrelloCredentials(BaseModel):
    api_key: Optional[str] = None  # omitted: keep the saved key
    token: Optional[str] = None


@router.put("/trello")
async def save_trello(body: TrelloCredentials, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Save the key (step 1) and, once the person has allowed access, the token (step 2)."""
    key = (body.api_key or "").strip() or tb.credentials(db)[0]
    if not key or len(key) < 20:
        raise HTTPException(400, "That doesn't look like a Trello API key.")
    set_settings(db, {"trello_api_key": key, "trello_token": (body.token or "").strip() or None})
    if body.token:
        try:
            account = await tb.whoami(db)
        except tb.TrelloError as exc:
            set_settings(db, {"trello_token": None})
            raise HTTPException(400, str(exc))
        return {"connected": True, "account": account}
    return {"connected": False, "authorize_url": tb.authorize_url(key)}


@router.delete("/trello")
def disconnect_trello(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    set_settings(db, {"trello_api_key": None, "trello_token": None})
    return {"connected": tb.connected(db)}


@router.get("/trello/boards")
async def trello_boards(db: Session = Depends(get_db), _: User = Depends(require_manager)):
    try:
        return await tb.list_boards(db)
    except tb.TrelloError as exc:
        _err(exc)


# ---- a team's board ------------------------------------------------------------

def _team(db: Session, team_id: str) -> Team:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found.")
    return team


def _can_view_team(db: Session, user: User, team: Team) -> bool:
    if access.is_manager(user) or team.id in access.led_team_ids(db, user):
        return True
    return bool(user.employee and user.employee.team_id == team.id)


class ListStatus(BaseModel):
    id: str
    status: str


class BoardChoice(BaseModel):
    source: str  # native | trello
    board_id: Optional[str] = None
    lists: Optional[List[ListStatus]] = None


@router.put("/teams/{team_id}/board")
async def choose_board(team_id: str, body: BoardChoice, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    team = _team(db, team_id)
    if body.source == "native":
        team.board_source = "native"
        db.commit()
        return {"source": "native"}
    if body.source != "trello" or not body.board_id:
        raise HTTPException(400, "Pick a Trello board.")
    try:
        await tb.connect_team(db, team, body.board_id)
        if body.lists:
            wanted = {l.id: l.status for l in body.lists if l.status in tb.STATUSES}
            team.board_lists = [{**l, "status": wanted.get(l["id"], l["status"])} for l in team.board_lists]
            db.commit()
        stats = await tb.sync_team(db, team)
    except tb.TrelloError as exc:
        _err(exc)
    return {"source": "trello", "board_name": team.board_name, "lists": team.board_lists, "synced": stats}


def _initials(name: str) -> str:
    parts = [p for p in (name or "?").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


@router.get("/teams/{team_id}/board")
async def team_board(team_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    team = _team(db, team_id)
    if not _can_view_team(db, user, team):
        raise HTTPException(404, "Team not found.")
    if team.board_source != "trello" or not team.board_id:
        return {"source": "native", "team_id": team.id}
    try:
        await tb.sync_team(db, team)
        data = await tb.fetch_board(db, team)
    except tb.TrelloError as exc:
        _err(exc)
    items = {w.external_id: w for w in db.scalars(
        select(WorkItem).where(WorkItem.external_provider == "trello", WorkItem.external_board_id == team.board_id))}
    people = {e.trello_member_id: e for e in db.scalars(select(Employee).where(Employee.trello_member_id.is_not(None)))}
    names = {m["id"]: m.get("fullName") or m.get("username") for m in data["members"]}
    today = date.today()
    lists = []
    for l in data["lists"]:
        cards = []
        for c in sorted((c for c in data["cards"] if c["idList"] == l["id"]), key=lambda c: c.get("pos", 0)):
            due = tb._due(c)
            item = items.get(c["id"])
            members = [{"id": mid, "name": names.get(mid) or "Someone", "initials": _initials(names.get(mid) or ""),
                        "employee_id": people[mid].id if mid in people else None} for mid in c.get("idMembers") or []]
            if not members and item and item.employee:  # no one on the card in Trello, but MeetPact knows the owner
                members = [{"id": None, "name": item.employee.name, "initials": _initials(item.employee.name),
                            "employee_id": item.employee.id, "meetpact_only": True}]
            cards.append({
                "id": c["id"], "title": c["name"], "url": c.get("shortUrl"), "due": due.isoformat() if due else None,
                "overdue": bool(due and due < today and not c.get("dueComplete")), "done": bool(c.get("dueComplete")),
                "item_id": item.id if item else None,
                "members": members,
            })
        lists.append({**l, "cards": cards})
    return {
        "source": "trello", "team_id": team.id, "board_name": team.board_name, "board_url": team.board_url,
        "synced_at": team.board_synced_at, "lists": lists,
        "members": [{"id": m["id"], "name": names[m["id"]],
                     "employee_id": people[m["id"]].id if m["id"] in people else None} for m in data["members"]],
    }


class CardMove(BaseModel):
    card_id: str
    list_id: str


@router.post("/teams/{team_id}/board/move")
async def move_card(team_id: str, body: CardMove, db: Session = Depends(get_db), user: User = Depends(current_user)):
    team = _team(db, team_id)
    if not _can_view_team(db, user, team) or team.board_source != "trello":
        raise HTTPException(404, "Team not found.")
    if body.list_id not in {l["id"] for l in team.board_lists or []}:
        raise HTTPException(400, "That list is not on this board.")
    try:
        await tb._call(db, "PUT", f"/cards/{body.card_id}", idList=body.list_id)
        await tb.sync_team(db, team)
    except tb.TrelloError as exc:
        _err(exc)
    return {"ok": True}


class MemberLink(BaseModel):
    member_id: str
    employee_id: Optional[str] = None


@router.put("/teams/{team_id}/board/members")
def link_member(team_id: str, body: MemberLink, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    """Say which MeetPact person a Trello member is (or nobody)."""
    _team(db, team_id)
    for e in db.scalars(select(Employee).where(Employee.trello_member_id == body.member_id)):
        e.trello_member_id = None
    if body.employee_id:
        emp = db.get(Employee, body.employee_id)
        if not emp:
            raise HTTPException(404, "Person not found.")
        emp.trello_member_id = body.member_id
    db.commit()
    return {"ok": True}
