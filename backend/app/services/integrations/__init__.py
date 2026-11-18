"""Optional task-tool integrations: ClickUp, Jira, Asana, Trello, monday.com.

Each provider can create a task from a work item and read that task's status
back. Sync maps the external status onto the work item, so finishing a task
in Jira also moves it on the progress tracker. A provider is enabled simply
by setting its environment variables.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Meeting, WorkItem, WorkItemEvent
from app.services.app_settings import get_setting
from app.services.integrations.base import IntegrationError, Provider, TaskRef
from app.services.integrations.providers import PROVIDERS

log = logging.getLogger(__name__)


def get_provider(name: str) -> Provider:
    p = PROVIDERS.get(name)
    if p is None:
        raise IntegrationError(f"Unknown integration '{name}'.")
    if not p.configured():
        raise IntegrationError(f"{p.label} is not configured. Set {', '.join(p.required_env)} in .env.")
    return p


def status_list() -> List[Dict]:
    return [
        {"name": p.name, "label": p.label, "configured": p.configured(), "required_env": p.required_env}
        for p in PROVIDERS.values()
    ]


async def push_item(db: Session, item: WorkItem, provider_name: str, actor: str = "user") -> WorkItem:
    if item.external_id:
        raise IntegrationError(f"Already linked to {item.external_provider}.")
    provider = get_provider(provider_name)
    assignee = item.employee.email if item.employee else None
    ref: TaskRef = await provider.create_task(
        title=item.title,
        description=(item.details or "") + f"\n\nCreated by MeetPact"
        + (f" for {item.employee.name}" if item.employee else ""),
        due=item.due_date,
        assignee_email=assignee,
    )
    item.external_provider = provider.name
    item.external_id = ref.id
    item.external_url = ref.url
    item.external_status = ref.status
    item.external_synced_at = datetime.now(timezone.utc)
    db.add(WorkItemEvent(work_item_id=item.id, kind="synced", note=f"Created in {provider.label}", actor=actor))
    db.commit()
    return item


async def sync_item(db: Session, item: WorkItem) -> Optional[str]:
    """Pull the external status; returns the new local status if it changed."""
    if not item.external_id or not item.external_provider:
        return None
    provider = get_provider(item.external_provider)
    raw, mapped = await provider.fetch_status(item.external_id)
    item.external_status = raw
    item.external_synced_at = datetime.now(timezone.utc)
    changed = None
    if mapped and mapped != item.status:
        from app.services.tracker import set_status

        set_status(db, item, mapped, None, f"{provider.label} status is now '{raw}'", actor=provider.label)
        changed = mapped
    db.commit()
    return changed


async def sync_all(db: Session) -> Dict[str, int]:
    counts = {"checked": 0, "changed": 0, "errors": 0, "boards": 0}
    # Teams whose task board is Trello: the whole board in one pass.
    from app.models import Team
    from app.services import trello_board

    for team in db.scalars(select(Team).where(Team.board_source == "trello", Team.board_id.is_not(None))).all():
        try:
            stats = await trello_board.sync_team(db, team)
            counts["boards"] += 1
            counts["changed"] += stats["created"] + stats["updated"] + stats["closed"]
        except trello_board.TrelloError as exc:
            counts["errors"] += 1
            log.info("board sync failed for team %s: %s", team.id, exc)
    # Single items pushed to a tool by hand (not part of a team board).
    items = db.scalars(select(WorkItem).where(WorkItem.external_id.is_not(None),
                                              WorkItem.external_board_id.is_(None))).all()
    for item in items:
        if item.status in ("completed", "dropped") and item.external_status:
            continue
        try:
            counts["checked"] += 1
            if await sync_item(db, item):
                counts["changed"] += 1
        except IntegrationError as exc:
            counts["errors"] += 1
            log.info("sync failed for %s: %s", item.id, exc)
    return counts


async def auto_push_new_items(db: Session, meeting: Meeting) -> None:
    provider_name = get_setting(db, "auto_push_provider")
    if not provider_name:
        return
    items = db.scalars(
        select(WorkItem).where(
            WorkItem.created_meeting_id == meeting.id,
            WorkItem.kind.in_(["action_item", "commitment"]),
            WorkItem.external_id.is_(None),
        )
    ).all()
    for item in items:
        try:
            await push_item(db, item, provider_name, actor="auto")
        except IntegrationError as exc:
            log.warning("Auto-push to %s failed: %s", provider_name, exc)
            return
