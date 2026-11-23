"""A team's Trello board as its task board.

When a team picks Trello (Team.board_source == "trello"), the Trello board is
the source of truth for that team's tasks:

* Every open card becomes a WorkItem (external_provider="trello"), so the
  dashboards, reports, Ask and the stand-up host see the same tasks. The card's
  list decides the status (via Team.board_lists), its members decide who owns
  it (Employee.trello_member_id, matched by name the first time).
* Work that meetings create for that team becomes cards; status changes the
  meeting analysis makes (e.g. "done") move the card to the matching list.
* The Work board shows the live Trello board for that team; dragging a card
  moves it in Trello.

Credentials: TRELLO_API_KEY / TRELLO_TOKEN in .env, else the ones saved from
the setup wizard (app settings "trello_api_key" / "trello_token").
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Employee, Team, WorkItem, WorkItemEvent
from app.services import identity
from app.services.app_settings import get_setting

log = logging.getLogger(__name__)

API = "https://api.trello.com/1"
TIMEOUT = 20.0
STATUSES = ("planned", "in_progress", "blocked", "completed", "ignore")
STATUS_LABEL = {"planned": "To do", "in_progress": "In progress", "blocked": "Blocked", "completed": "Done"}


class TrelloError(Exception):
    pass


def credentials(db: Session) -> Tuple[Optional[str], Optional[str]]:
    key = settings.TRELLO_API_KEY or get_setting(db, "trello_api_key")
    token = settings.TRELLO_TOKEN or get_setting(db, "trello_token")
    return key, token


def connected(db: Session) -> bool:
    key, token = credentials(db)
    return bool(key and token)


def authorize_url(key: str) -> str:
    """Trello's page that shows a token after "Allow" (read and write, no expiry)."""
    return (f"https://trello.com/1/authorize?expiration=never&scope=read,write&response_type=token"
            f"&name=MeetPact&key={key}")


async def _call(db: Session, method: str, path: str, **params: Any) -> Any:
    key, token = credentials(db)
    if not (key and token):
        raise TrelloError("Trello is not connected. Add the API key and token under Admin or in .env.")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.request(method, f"{API}{path}", params={"key": key, "token": token, **params})
    except httpx.HTTPError as exc:
        raise TrelloError(f"Could not reach Trello ({exc.__class__.__name__}).") from exc
    if resp.status_code in (401, 403):
        raise TrelloError("Trello rejected the API key or token.")
    if resp.status_code == 404:
        raise TrelloError("Trello could not find that board, list or card.")
    if resp.status_code >= 400:
        raise TrelloError(f"Trello returned {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.content else {}


async def whoami(db: Session) -> str:
    me = await _call(db, "GET", "/members/me", fields="fullName,username")
    return me.get("fullName") or me.get("username") or "Trello"


async def list_boards(db: Session) -> List[Dict]:
    boards = await _call(db, "GET", "/members/me/boards", filter="open", fields="name,url")
    return [{"id": b["id"], "name": b["name"], "url": b.get("url")} for b in boards]


def guess_status(list_name: str) -> str:
    n = (list_name or "").lower()
    if re.search(r"\b(done|complete|completed|finished|shipped|closed)\b", n):
        return "completed"
    if re.search(r"\b(block|blocked|stuck|waiting|on hold)\b", n):
        return "blocked"
    if re.search(r"\b(doing|progress|wip|review|testing|in dev|working)\b", n):
        return "in_progress"
    if re.search(r"\b(descoped|archive|archived|postponed|won'?t)\b", n):
        return "ignore"
    return "planned"


async def board_lists(db: Session, board_id: str, previous: Optional[List[Dict]] = None) -> List[Dict]:
    """The board's open lists with a status each: kept from `previous`, else guessed."""
    known = {l["id"]: l.get("status") for l in previous or []}
    lists = await _call(db, "GET", f"/boards/{board_id}/lists", filter="open", fields="name,pos")
    return [{"id": l["id"], "name": l["name"], "status": known.get(l["id"]) or guess_status(l["name"])} for l in lists]


async def connect_team(db: Session, team: Team, board_id: str) -> Team:
    board = await _call(db, "GET", f"/boards/{board_id}", fields="name,url")
    team.board_source = "trello"
    previous = team.board_lists if team.board_id == board_id else None
    team.board_id, team.board_name, team.board_url = board_id, board.get("name"), board.get("url")
    team.board_lists = await board_lists(db, board_id, previous)
    db.commit()
    return team


# ---- reading the board -----------------------------------------------------

def _member_map(db: Session, team: Team, members: List[Dict]) -> Dict[str, Optional[Employee]]:
    """Trello member id -> MeetPact person. Unmapped members are matched by
    name once, among this team's people first, then everyone."""
    people = list(db.scalars(select(Employee).where(Employee.active.is_(True))))
    by_trello = {e.trello_member_id: e for e in people if e.trello_member_id}
    team_people = [e for e in people if e.team_id == team.id]
    out: Dict[str, Optional[Employee]] = {}
    for m in members:
        emp = by_trello.get(m["id"])
        if emp is None:
            for pool in (team_people, people):
                emp = (identity.match_employee(m.get("fullName") or "", [e for e in pool if not e.trello_member_id])
                       or identity.match_employee(m.get("username") or "", [e for e in pool if not e.trello_member_id]))
                if emp:
                    emp.trello_member_id = m["id"]
                    by_trello[m["id"]] = emp
                    break
        out[m["id"]] = emp
    return out


async def fetch_board(db: Session, team: Team) -> Dict:
    """Live board: lists, open cards with their members, and the board's members."""
    if team.board_source != "trello" or not team.board_id:
        raise TrelloError("This team does not use a Trello board.")
    cards = await _call(db, "GET", f"/boards/{team.board_id}/cards", filter="open",
                        fields="name,desc,idList,idMembers,due,dueComplete,shortUrl,pos,dateLastActivity")
    members = await _call(db, "GET", f"/boards/{team.board_id}/members", fields="fullName,username")
    lists = await board_lists(db, team.board_id, team.board_lists)
    if lists != team.board_lists:
        team.board_lists = lists
    return {"lists": lists, "cards": cards, "members": members}


def _due(card: Dict) -> Optional[date]:
    raw = card.get("due")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _event(db: Session, item: WorkItem, kind: str, detail: str, new_status: Optional[str] = None,
           old_status: Optional[str] = None) -> None:
    kind = "status_changed" if kind == "status" else kind
    db.add(WorkItemEvent(work_item_id=item.id, kind=kind, note=detail, actor="Trello",
                         from_status=old_status, to_status=new_status))


async def sync_team(db: Session, team: Team) -> Dict[str, int]:
    """Bring the team's Trello cards into MeetPact. Returns counts."""
    data = await fetch_board(db, team)
    status_of = {l["id"]: l["status"] for l in data["lists"]}
    list_name = {l["id"]: l["name"] for l in data["lists"]}
    owners = _member_map(db, team, data["members"])
    names = {m["id"]: m.get("fullName") or m.get("username") for m in data["members"]}
    card_ids = [c["id"] for c in data["cards"]]
    # Cards already linked (this board, or pushed to Trello by hand before the
    # team switched to its board) are updated, never imported twice.
    existing = {w.external_id: w for w in db.scalars(
        select(WorkItem).where(WorkItem.external_provider == "trello",
                               (WorkItem.external_board_id == team.board_id) | WorkItem.external_id.in_(card_ids)))}
    stats = {"created": 0, "updated": 0, "closed": 0}
    seen = set()
    now = datetime.now(timezone.utc)
    for card in data["cards"]:
        list_status = status_of.get(card["idList"], "planned")
        if list_status == "ignore":
            continue
        seen.add(card["id"])
        status = "completed" if card.get("dueComplete") else list_status
        members = [{"id": mid, "name": names.get(mid) or "Someone",
                    "employee_id": owners[mid].id if owners.get(mid) else None} for mid in card.get("idMembers") or []]
        owner = next((owners[m["id"]] for m in members if owners.get(m["id"])), None)
        item = existing.get(card["id"])
        if item is None:
            item = WorkItem(title=card["name"][:500], details=card.get("desc") or "", kind="task", status=status,
                            source="manual", external_provider="trello", external_id=card["id"],
                            employee_id=owner.id if owner else None)
            db.add(item)
            db.flush()
            _event(db, item, "created", f"Imported from Trello list \"{list_name.get(card['idList'], '')}\".",
                   new_status=status)
            stats["created"] += 1
        else:
            changed = False
            if item.status != status:
                _event(db, item, "status", f"Moved to \"{list_name.get(card['idList'], '')}\" in Trello.",
                       new_status=status, old_status=item.status)
                item.status = status
                changed = True
            if item.title != card["name"][:500]:
                item.title, changed = card["name"][:500], True
            if owner and item.employee_id != owner.id:
                item.employee_id, changed = owner.id, True
            stats["updated"] += changed
        item.due_date = _due(card)
        item.completed_at = item.completed_at or (now if status == "completed" else None)
        if status != "completed":
            item.completed_at = None
        item.external_url = card.get("shortUrl")
        item.external_board_id = team.board_id
        item.external_list_id = card["idList"]
        item.external_status = list_name.get(card["idList"])
        item.external_members = members
        item.external_synced_at = now
    # Cards archived or deleted in Trello (or moved to an ignored list).
    for card_id, item in existing.items():
        if card_id not in seen and item.status not in ("completed", "dropped"):
            _event(db, item, "status", "Archived or removed in Trello.", new_status="dropped", old_status=item.status)
            item.status = "dropped"
            stats["closed"] += 1
    team.board_synced_at = now
    db.commit()
    return stats


# ---- writing to the board ----------------------------------------------------

def list_for_status(team: Team, status: str) -> Optional[str]:
    for l in team.board_lists or []:
        if l.get("status") == status:
            return l["id"]
    if status == "blocked":  # no Blocked list: keep it with the in-progress work
        return list_for_status(team, "in_progress")
    return None


def team_for_item(db: Session, item: WorkItem, fallback_team_id: Optional[str] = None) -> Optional[Team]:
    team_id = (item.employee.team_id if item.employee else None) or fallback_team_id
    team = db.get(Team, team_id) if team_id else None
    return team if team and team.board_source == "trello" and team.board_id else None


async def create_card(db: Session, item: WorkItem, team: Team) -> None:
    list_id = list_for_status(team, item.status) or list_for_status(team, "planned") or \
        next((l["id"] for l in team.board_lists or [] if l.get("status") != "ignore"), None)
    if not list_id:
        raise TrelloError(f"The board \"{team.board_name}\" has no list to put new cards in.")
    params: Dict[str, Any] = {"idList": list_id, "name": item.title, "desc": item.details or ""}
    if item.due_date:
        params["due"] = item.due_date.isoformat()
    if item.employee and item.employee.trello_member_id:
        params["idMembers"] = item.employee.trello_member_id
    card = await _call(db, "POST", "/cards", **params)
    item.external_provider, item.external_id = "trello", card["id"]
    item.external_url, item.external_board_id, item.external_list_id = card.get("shortUrl"), team.board_id, list_id
    item.external_status = next((l["name"] for l in team.board_lists if l["id"] == list_id), None)
    item.external_members = ([{"id": item.employee.trello_member_id, "name": item.employee.name,
                               "employee_id": item.employee.id}] if params.get("idMembers") else [])
    item.external_synced_at = datetime.now(timezone.utc)
    _event(db, item, "synced", f"Card created on the Trello board \"{team.board_name}\".")


async def move_card(db: Session, item: WorkItem, team: Team, status: str) -> bool:
    """Move the item's card to the list for `status`. False when no list matches."""
    list_id = list_for_status(team, status)
    if not list_id or not item.external_id:
        return False
    if list_id != item.external_list_id:
        await _call(db, "PUT", f"/cards/{item.external_id}", idList=list_id)
        item.external_list_id = list_id
        item.external_status = next((l["name"] for l in team.board_lists if l["id"] == list_id), None)
    return True


async def push_meeting_changes(db: Session, meeting) -> Dict[str, int]:
    """After a meeting's analysis: work first raised in this meeting becomes
    cards, and status changes move existing cards. Older work that was never on
    the board is left alone (it would flood the board with history). Failures
    are logged, never raised."""
    stats = {"cards": 0, "moved": 0}
    from app.services.app_settings import get_setting

    if not get_setting(db, "board_from_meetings"):
        return stats  # people manage the board
    items = db.scalars(select(WorkItem).where(
        (WorkItem.created_meeting_id == meeting.id) | (WorkItem.last_meeting_id == meeting.id))).all()
    for item in items:
        team = team_for_item(db, item, meeting.team_id)
        if not team or item.status == "dropped":
            continue
        try:
            if not item.external_id:
                if item.created_meeting_id != meeting.id:
                    continue
                await create_card(db, item, team)
                stats["cards"] += 1
            elif item.external_provider == "trello" and item.external_board_id == team.board_id:
                current = next((l.get("status") for l in team.board_lists if l["id"] == item.external_list_id), None)
                if current != item.status and await move_card(db, item, team, item.status):
                    _event(db, item, "synced", f"Moved to \"{item.external_status}\" in Trello after the meeting.")
                    stats["moved"] += 1
        except TrelloError as exc:
            log.warning("Trello update for a work item failed: %s", exc)
    db.commit()
    return stats


# ---- for the stand-up host -----------------------------------------------------

def board_brief(db: Session, team: Optional[Team], limit: int = 40) -> Optional[str]:
    """Plain-text summary of open cards and who owns them (from the last sync)."""
    if not team or team.board_source != "trello" or not team.board_id:
        return None
    items = db.scalars(select(WorkItem).where(
        WorkItem.external_board_id == team.board_id,
        WorkItem.status.in_(["planned", "in_progress", "blocked"])).order_by(WorkItem.due_date)).all()
    if not items:
        return f'The team\'s Trello board "{team.board_name}" has no open cards.'
    by_owner: Dict[str, List[str]] = {}
    today = date.today()
    for w in items[:limit]:
        names = ([m["name"] for m in (w.external_members or [])]
                 or ([w.employee.name] if w.employee else ["Unassigned"]))
        due = f", due {w.due_date.isoformat()}" + (" (overdue)" if w.due_date < today else "") if w.due_date else ""
        line = f'"{w.title}" ({STATUS_LABEL.get(w.status, w.status)}{due})'
        for n in names:
            by_owner.setdefault(n, []).append(line)
    parts = [f'Open cards on the team\'s Trello board "{team.board_name}" ({len(items)} open):']
    for owner in sorted(by_owner, key=lambda n: (n == "Unassigned", n)):
        parts.append(f"- {owner}: " + "; ".join(by_owner[owner]))
    return "\n".join(parts)
