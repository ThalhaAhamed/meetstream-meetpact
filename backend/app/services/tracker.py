"""Apply a meeting analysis to the long-lived progress records."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Blocker,
    Employee,
    EmployeeUpdate,
    Meeting,
    Project,
    WorkItem,
    WorkItemEvent,
)
from app.services import identity
from app.services.extraction import MeetingAnalysis

log = logging.getLogger(__name__)

OPEN_STATUSES = ("planned", "in_progress", "blocked")


def _date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _similar(a: str, b: str) -> float:
    na = re.sub(r"[^a-z0-9 ]", "", a.lower())
    nb = re.sub(r"[^a-z0-9 ]", "", b.lower())
    return SequenceMatcher(None, na, nb).ratio()


def open_items(db: Session, employee_id: str) -> List[WorkItem]:
    return list(
        db.scalars(
            select(WorkItem)
            .where(WorkItem.employee_id == employee_id, WorkItem.status.in_(OPEN_STATUSES))
            .order_by(WorkItem.created_at)
        )
    )


def open_blockers(db: Session, employee_id: str) -> List[Blocker]:
    return list(db.scalars(select(Blocker).where(Blocker.employee_id == employee_id, Blocker.status == "open")))


def roster_context(db: Session, meeting: Meeting, employee_ids: List[str]) -> List[dict]:
    """What the model needs to know about each attendee before the meeting."""
    out = []
    for emp in db.scalars(select(Employee).where(Employee.id.in_(employee_ids))):
        entry = {
            "employee_id": emp.id,
            "name": emp.name,
            "also_known_as": emp.aliases or [],
            "title": emp.title,
            "open_work_items": [
                {
                    "id": w.id,
                    "title": w.title,
                    "status": w.status,
                    "due_date": w.due_date,
                    "carried_over_meetings": w.carry_count,
                }
                for w in open_items(db, emp.id)
            ],
            "open_blockers": [{"id": b.id, "description": b.description} for b in open_blockers(db, emp.id)],
        }
        out.append(entry)
    return out


def _project_for(db: Session, name: Optional[str], fallback: Optional[str]) -> Optional[str]:
    if name:
        target = name.lower().strip()
        for p in db.scalars(select(Project)):
            words = [p.name.lower(), *[k.lower() for k in (p.keywords or [])]]
            if any(target == w or (len(w) > 3 and w in target) or (len(target) > 3 and target in w) for w in words):
                return p.id
    return fallback


def _event(db: Session, item: WorkItem, kind: str, meeting: Optional[Meeting], note: str = "", frm=None, to=None, actor="ai"):
    db.add(
        WorkItemEvent(
            work_item_id=item.id,
            meeting_id=meeting.id if meeting else None,
            kind=kind,
            from_status=frm,
            to_status=to,
            note=note,
            actor=actor,
        )
    )


def set_status(db: Session, item: WorkItem, status: str, meeting: Optional[Meeting], note: str, actor: str = "ai") -> None:
    if status == item.status:
        return
    _event(db, item, "status_changed", meeting, note, item.status, status, actor)
    item.status = status
    item.completed_at = datetime.now(timezone.utc) if status == "completed" else None


def create_item(
    db: Session,
    *,
    employee_id: Optional[str],
    title: str,
    status: str,
    meeting: Optional[Meeting],
    due: Optional[date] = None,
    project_id: Optional[str] = None,
    kind: str = "task",
    source: str = "ai",
    actor: str = "ai",
) -> WorkItem:
    item = WorkItem(
        employee_id=employee_id,
        title=title.strip()[:500],
        status=status,
        due_date=due,
        project_id=project_id,
        kind=kind,
        source=source,
        created_meeting_id=meeting.id if meeting else None,
        last_meeting_id=meeting.id if meeting else None,
        completed_at=datetime.now(timezone.utc) if status == "completed" else None,
    )
    db.add(item)
    db.flush()
    _event(db, item, "created", meeting, f"Recorded as {status.replace('_', ' ')}", None, status, actor)
    return item


_FILLER = {
    "a", "an", "the", "to", "of", "on", "for", "and", "in", "with", "my", "our", "their", "this", "that", "it",
    "work", "working", "address", "fix", "handle", "do", "finish", "complete", "start", "continue", "look", "into",
    "task", "item", "issue", "problem", "some", "current", "is", "be", "get", "today", "tomorrow",
    "will", "done", "all", "stuff", "things", "everything",
}


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _FILLER and len(w) > 1}


def _word_overlap(a: str, b: str) -> float:
    """Share of the shorter title's content words found in the other title, so
    'Work on the improper response time' matches 'Address improper response time'."""
    wa, wb = _content_words(a), _content_words(b)
    if len(wa) < 2 or len(wb) < 2:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _find_duplicate(items: List[WorkItem], title: str) -> Optional[WorkItem]:
    best, score = None, 0.0
    for w in items:
        s = max(_similar(w.title, title), 0.82 if _word_overlap(w.title, title) >= 0.99 else 0.0)
        if s > score:
            best, score = w, s
    return best if score >= 0.82 else None


def apply_analysis(db: Session, meeting: Meeting, analysis: MeetingAnalysis, excluded_names: set[str]) -> Dict[str, int]:
    """Write updates, work items and blockers. Returns counters for the log."""
    stats = {"updates": 0, "items_created": 0, "items_updated": 0, "carried_over": 0, "blockers": 0}
    employees = identity.active_employees(db)
    by_id = {e.id: e for e in employees}

    # Re-processing replaces this meeting's updates, and the work items the AI
    # created from it that nobody has touched since (anything a person edited,
    # or a later meeting moved, is kept).
    for old in db.scalars(select(EmployeeUpdate).where(EmployeeUpdate.meeting_id == meeting.id)):
        db.delete(old)
    for item in db.scalars(select(WorkItem).where(WorkItem.created_meeting_id == meeting.id, WorkItem.source == "ai")):
        if all(ev.actor == "ai" and ev.meeting_id == meeting.id for ev in item.events) and not item.external_id:
            db.delete(item)
    for b in db.scalars(select(Blocker).where(Blocker.raised_meeting_id == meeting.id, Blocker.status == "open")):
        if b.mention_count <= 1 and b.last_meeting_id in (None, meeting.id):
            db.delete(b)
    db.flush()

    reported: set[str] = set()
    touched_items: set[str] = set()

    for rep in analysis.employee_reports:
        if identity.norm(rep.speaker_name) in excluded_names:
            continue
        emp = by_id.get(rep.employee_id or "") or identity.match_employee(rep.speaker_name, employees)
        if emp is None or emp.id in reported:
            continue
        reported.add(emp.id)
        db.add(
            EmployeeUpdate(
                meeting_id=meeting.id,
                employee_id=emp.id,
                slot=meeting.slot,
                meeting_date=meeting.meeting_date,
                summary=rep.summary,
                completed=rep.completed,
                in_progress=rep.in_progress,
                planned=rep.planned,
                pending=rep.pending,
                blockers=rep.blockers,
                commitments=[c.model_dump() for c in rep.commitments],
            )
        )
        stats["updates"] += 1

        current = {w.id: w for w in open_items(db, emp.id)}
        for upd in rep.existing_item_updates:
            item = current.get(upd.work_item_id) or db.get(WorkItem, upd.work_item_id)
            if item is None or item.employee_id != emp.id:
                continue
            touched_items.add(item.id)
            item.last_meeting_id = meeting.id
            new_due = _date(upd.due_date)
            if new_due and new_due != item.due_date:
                _event(db, item, "due_changed", meeting, f"Deadline {item.due_date or 'none'} → {new_due}")
                item.due_date = new_due
            if upd.new_status == "unchanged":
                _event(db, item, "mentioned", meeting, upd.note)
            else:
                set_status(db, item, upd.new_status, meeting, upd.note)
            stats["items_updated"] += 1

        open_now = open_items(db, emp.id)
        for new in rep.new_work_items:
            dup = _find_duplicate(open_now, new.title)
            if dup:
                touched_items.add(dup.id)
                dup.last_meeting_id = meeting.id
                if new.status != dup.status:
                    set_status(db, dup, new.status, meeting, "Updated in meeting")
                continue
            item = create_item(
                db,
                employee_id=emp.id,
                title=new.title,
                status=new.status,
                meeting=meeting,
                due=_date(new.due_date),
                project_id=_project_for(db, new.project, meeting.project_id),
            )
            touched_items.add(item.id)
            open_now.append(item)
            stats["items_created"] += 1

        # Backstop: models sometimes list work only in the update's
        # completed / in_progress / planned lists and leave new_work_items
        # empty (seen live with Gemini). Track those too, matching existing
        # open items first so nothing is duplicated.
        for status, texts in (("completed", rep.completed), ("in_progress", rep.in_progress), ("planned", rep.planned)):
            for text in texts:
                # "Finish the current task today" names no work: not trackable on its own.
                vague = len(_content_words(text)) < 2
                dup = _find_duplicate(open_now, text) or _find_duplicate(
                    [w for w in db.scalars(select(WorkItem).where(WorkItem.id.in_(touched_items)))], text)
                if dup:
                    if dup.id not in touched_items and dup.status != status:
                        set_status(db, dup, status, meeting, "Reported in meeting")
                    touched_items.add(dup.id)
                    dup.last_meeting_id = meeting.id
                    continue
                if vague:
                    continue
                item = create_item(db, employee_id=emp.id, title=text, status=status, meeting=meeting,
                                   project_id=_project_for(db, None, meeting.project_id))
                touched_items.add(item.id)
                open_now.append(item)
                stats["items_created"] += 1

        # A commitment whose deadline was already put on an existing item is that
        # item's deadline, not a new task (seen live: "done this evening").
        dated_here = {upd.due_date[:10] for upd in rep.existing_item_updates if upd.due_date}
        for c in rep.commitments:
            if _find_duplicate(open_items(db, emp.id), c.text):
                continue
            if c.due_date and c.due_date[:10] in dated_here:
                continue
            item = create_item(
                db, employee_id=emp.id, title=c.text, status="planned", meeting=meeting,
                due=_date(c.due_date), project_id=meeting.project_id, kind="commitment",
            )
            touched_items.add(item.id)
            stats["items_created"] += 1

        # Blockers
        existing = open_blockers(db, emp.id)
        for bid in rep.resolved_blocker_ids:
            b = next((x for x in existing if x.id == bid), None)
            if b:
                b.status = "resolved"
                b.resolved_meeting_id = meeting.id
                b.resolved_at = datetime.now(timezone.utc)
        for text in rep.blockers:
            match = next((b for b in existing if b.status == "open" and _similar(b.description, text) >= 0.7), None)
            if match:
                if match.raised_meeting_id != meeting.id and match.last_meeting_id != meeting.id:
                    match.mention_count += 1
                    match.last_meeting_id = meeting.id
                continue
            db.add(Blocker(employee_id=emp.id, project_id=meeting.project_id, description=text,
                           raised_meeting_id=meeting.id, last_meeting_id=meeting.id))
            stats["blockers"] += 1

    # Action items not already captured as someone's work item.
    for ai in analysis.action_items:
        owner = by_id.get(ai.owner_employee_id or "") or (
            identity.match_employee(ai.owner_name, employees) if ai.owner_name else None
        )
        if owner and identity.norm(owner.name) in excluded_names:
            continue
        pool = open_items(db, owner.id) if owner else list(
            db.scalars(select(WorkItem).where(WorkItem.employee_id.is_(None), WorkItem.status.in_(OPEN_STATUSES)))
        )
        dup = _find_duplicate(pool, ai.title)
        if dup:
            if ai.due_date and not dup.due_date:
                dup.due_date = _date(ai.due_date)
            continue
        create_item(
            db, employee_id=owner.id if owner else None, title=ai.title, status="planned", meeting=meeting,
            due=_date(ai.due_date), project_id=meeting.project_id, kind="action_item",
        )
        stats["items_created"] += 1

    # Carry-forward: open items of people who reported here but whose items
    # were not discussed stay open and are flagged as carried over.
    for emp_id in reported:
        for item in open_items(db, emp_id):
            if item.id in touched_items or item.created_meeting_id == meeting.id:
                continue
            if item.last_meeting_id == meeting.id:
                continue
            item.carry_count += 1
            item.last_meeting_id = meeting.id
            _event(db, item, "carried_over", meeting, "Still open; not reported as finished in this meeting")
            stats["carried_over"] += 1

    db.flush()
    return stats
