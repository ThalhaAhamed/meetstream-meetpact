"""Meeting reports and period reports."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Blocker,
    Employee,
    EmployeeUpdate,
    Meeting,
    Project,
    Team,
    WorkItem,
    WorkItemEvent,
)

OPEN = ("planned", "in_progress", "blocked")


def _bullets(items: List[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- _None_"


MODE_LABELS = {"standup": "Stand-up", "notetaker": "Meeting"}


def _clean(items: Any) -> List[str]:
    return [str(i).strip() for i in (items or []) if str(i or "").strip()]


def _commitment(c: Dict[str, Any]) -> str:
    due = c.get("due_date") or c.get("due")
    return f"{c.get('text') or ''}" + (f" (due {due})" if due else "")


def person_sections(u: EmployeeUpdate) -> List[Tuple[str, List[str]]]:
    """(label, items) for one person's update, empty sections left out.
    "Still pending" lists only what isn't already done, in progress or planned,
    so the same task doesn't appear twice."""
    done, doing, planned = _clean(u.completed), _clean(u.in_progress), _clean(u.planned)
    seen = {i.lower() for i in done + doing + planned}
    sections = [
        ("Completed", done),
        ("In progress", doing),
        ("Planned next", planned),
        ("Still pending", [i for i in _clean(u.pending) if i.lower() not in seen]),
        ("Blockers", _clean(u.blockers)),
        ("Commitments", _clean(_commitment(c) for c in (u.commitments or []) if isinstance(c, dict))),
    ]
    return [(label, items) for label, items in sections if items]


def _review_note(u: EmployeeUpdate) -> str:
    if u.review_status == "unreviewed":
        return ""
    return f"Reviewed by {u.employee.name}: {u.review_status}." + (f" {u.employee_note}" if u.employee_note else "")


def employee_section_md(u: EmployeeUpdate) -> str:
    parts = [f"### {u.employee.name}", u.summary or ""]
    parts += [f"**{label}**\n" + "\n".join(f"- {i}" for i in items) for label, items in person_sections(u)]
    note = _review_note(u)
    if note:
        parts.append(f"_{note}_")
    return "\n\n".join(p for p in parts if p)


def action_text(a: Dict[str, str], bold_owner: bool = False) -> str:
    owner = (f"**{a['owner']}**" if bold_owner else a["owner"]) if a["owner"] else ""
    return a["title"] + (f" - {owner}" if owner else "") + (f" (due {a['due']})" if a["due"] else "")


def meeting_report_data(db: Session, meeting: Meeting, visible_employee: Optional[Callable[[str], bool]] = None) -> Dict[str, Any]:
    """Everything a meeting report shows, for one reader; the Markdown, email and
    Slack versions are all drawn from this. ``visible_employee(employee_id) -> bool``
    filters the per-person updates."""
    s = meeting.summary or {}
    when = meeting.started_at or meeting.scheduled_at or meeting.created_at
    actions = [
        {"title": a["title"].strip(), "owner": a.get("owner_name") or "", "due": a.get("due_date") or ""}
        for a in (s.get("action_items") or []) if isinstance(a, dict) and (a.get("title") or "").strip()
    ]
    updates = list(db.scalars(select(EmployeeUpdate).where(EmployeeUpdate.meeting_id == meeting.id)))
    shown = [u for u in updates if visible_employee is None or visible_employee(u.employee_id)]
    stats = s.get("stats") or {}
    counts = [(stats.get("items_created", 0), "new work item", "new work items"),
              (stats.get("items_updated", 0), "updated", "updated"),
              (stats.get("carried_over", 0), "carried over", "carried over"),
              (stats.get("blockers", 0), "new blocker", "new blockers")]
    mode = MODE_LABELS.get(meeting.mode, (meeting.mode or "meeting").capitalize())
    slot = meeting.slot if meeting.slot and meeting.slot != "general" else ""
    return {
        "title": meeting.title,
        "when_text": f"{when:%a %d %b %Y, %H:%M} UTC" if when else "",
        "kind": mode + (f" · {slot}" if slot else ""),
        "attendees": [(p.employee.name if p.employee else p.display_name) for p in meeting.participants if not p.is_bot],
        "overview": (s.get("overview") or "").strip(),
        "key_points": _clean(s.get("key_points")),
        "decisions": _clean(s.get("decisions")),
        "actions": actions,
        "open_questions": _clean(s.get("open_questions")),
        "updates": shown,
        "people": [{"name": u.employee.name, "summary": (u.summary or "").strip(), "sections": person_sections(u),
                    "review": _review_note(u)} for u in shown],
        "hidden": len(updates) - len(shown),
        "progress": ", ".join(f"{n} {one if n == 1 else many}" for n, one, many in counts if n),
    }


def render_meeting_report(db: Session, meeting: Meeting, visible_employee: Optional[Callable[[str], bool]] = None) -> str:
    """Markdown report, shown in the app and downloadable. Empty sections are left out."""
    d = meeting_report_data(db, meeting, visible_employee)
    md = [f"# {d['title']}", " · ".join(x for x in (d["when_text"], d["kind"]) if x)]
    if d["attendees"]:
        md.append(f"**Attendees:** {', '.join(d['attendees'])}")
    md.append("## Summary\n" + (d["overview"] or "_No summary_"))
    for title, items in (("Key discussion points", d["key_points"]), ("Decisions", d["decisions"]),
                         ("Action items", [action_text(a, bold_owner=True) for a in d["actions"]]),
                         ("Open questions", d["open_questions"])):
        if items:
            md.append(f"## {title}\n" + "\n".join(f"- {i}" for i in items))
    people = "\n\n".join(employee_section_md(u) for u in d["updates"])
    if people or d["hidden"]:
        md.append("## Updates by person" + (f"\n\n{people}" if people else "")
                  + (f"\n\n_{d['hidden']} individual update(s) not shared with you._" if d["hidden"] else ""))
    if d["progress"]:
        md.append(f"## Progress tracking\n{d['progress']}")
    return "\n\n".join(md) + "\n"


# ---------------------------------------------------------------------------
# Period reports
# ---------------------------------------------------------------------------

def period_bounds(period: str, anchor: date) -> tuple[date, date]:
    if period == "daily":
        return anchor, anchor
    if period == "weekly":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "monthly":
        start = anchor.replace(day=1)
        nxt = (start + timedelta(days=32)).replace(day=1)
        return start, nxt - timedelta(days=1)
    raise ValueError("period must be daily, weekly or monthly")


def period_report(
    db: Session,
    period: str,
    anchor: date,
    *,
    employee_ids: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    team_id: Optional[str] = None,
) -> Dict[str, Any]:
    start, end = period_bounds(period, anchor)
    t0 = datetime.combine(start, time.min, tzinfo=timezone.utc)
    t1 = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)

    emp_q = select(Employee).where(Employee.active.is_(True))
    if team_id:
        emp_q = emp_q.where(Employee.team_id == team_id)
    if employee_ids is not None:
        emp_q = emp_q.where(Employee.id.in_(employee_ids))
    employees = list(db.scalars(emp_q.order_by(Employee.name)))
    ids = [e.id for e in employees]

    meetings_q = select(Meeting).where(
        or_(
            and_(Meeting.meeting_date >= start, Meeting.meeting_date <= end),
            and_(Meeting.meeting_date.is_(None), Meeting.created_at >= t0, Meeting.created_at < t1),
        ),
        Meeting.processing_status == "done",
    )
    if team_id:
        meetings_q = meetings_q.where(Meeting.team_id == team_id)
    if project_id:
        meetings_q = meetings_q.where(Meeting.project_id == project_id)
    meetings = list(db.scalars(meetings_q.order_by(Meeting.scheduled_at)))

    item_q = select(WorkItem).where(WorkItem.employee_id.in_(ids))
    if project_id:
        item_q = item_q.where(WorkItem.project_id == project_id)
    items = list(db.scalars(item_q))

    per_emp: Dict[str, Dict[str, Any]] = {
        e.id: {"employee_id": e.id, "name": e.name, "completed": [], "open": [], "overdue": [], "new": [],
               "carried_over": [], "blockers": [], "updates": 0}
        for e in employees
    }
    for w in items:
        r = per_emp.get(w.employee_id)
        if not r:
            continue
        created = w.created_at if w.created_at.tzinfo else w.created_at.replace(tzinfo=timezone.utc)
        completed_at = w.completed_at and (w.completed_at if w.completed_at.tzinfo else w.completed_at.replace(tzinfo=timezone.utc))
        if completed_at and t0 <= completed_at < t1:
            r["completed"].append(w.title)
        if w.status in OPEN:
            r["open"].append(w.title)
            # Overdue = deadline already passed (and within the period).
            if w.due_date and w.due_date < date.today() and w.due_date <= end:
                r["overdue"].append(f"{w.title} (due {w.due_date})")
            if w.carry_count >= 2:
                r["carried_over"].append(f"{w.title} (×{w.carry_count})")
        if t0 <= created < t1:
            r["new"].append(w.title)
    for b in db.scalars(select(Blocker).where(Blocker.employee_id.in_(ids), Blocker.status == "open")):
        per_emp[b.employee_id]["blockers"].append(b.description)
    for u in db.scalars(
        select(EmployeeUpdate).where(
            EmployeeUpdate.employee_id.in_(ids), EmployeeUpdate.meeting_date >= start, EmployeeUpdate.meeting_date <= end
        )
    ):
        per_emp[u.employee_id]["updates"] += 1

    totals = {
        "meetings": len(meetings),
        "completed": sum(len(r["completed"]) for r in per_emp.values()),
        "open": sum(len(r["open"]) for r in per_emp.values()),
        "overdue": sum(len(r["overdue"]) for r in per_emp.values()),
        "blockers": sum(len(r["blockers"]) for r in per_emp.values()),
        "new": sum(len(r["new"]) for r in per_emp.values()),
    }
    decisions = [{"meeting": m.title, "decision": d} for m in meetings for d in (m.summary or {}).get("decisions", [])]
    scope = (
        db.get(Project, project_id).name if project_id and db.get(Project, project_id)
        else db.get(Team, team_id).name if team_id and db.get(Team, team_id)
        else employees[0].name if employee_ids is not None and len(employees) == 1
        else "All teams"
    )
    report = {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "scope": scope,
        "totals": totals,
        "employees": list(per_emp.values()),
        "meetings": [{"id": m.id, "title": m.title, "date": (m.meeting_date or m.created_at.date()).isoformat(), "slot": m.slot} for m in meetings],
        "decisions": decisions,
    }
    report["markdown"] = period_report_md(report)
    return report


def period_report_md(r: Dict[str, Any]) -> str:
    t = r["totals"]
    lines = [
        f"# {r['period'].title()} progress report - {r['scope']}",
        f"{r['start']} to {r['end']}",
        "",
        f"- Meetings analysed: {t['meetings']}",
        f"- Work items completed: {t['completed']}",
        f"- New work items: {t['new']}",
        f"- Open work items: {t['open']} ({t['overdue']} overdue)",
        f"- Open blockers: {t['blockers']}",
        "",
    ]
    for e in r["employees"]:
        if not (e["completed"] or e["open"] or e["blockers"] or e["updates"]):
            continue
        lines.append(f"## {e['name']}")
        lines.append(f"Updates given: {e['updates']}")
        lines.append("**Completed**\n" + _bullets(e["completed"]))
        lines.append("**Open**\n" + _bullets(e["open"]))
        if e["overdue"]:
            lines.append("**Overdue**\n" + _bullets(e["overdue"]))
        if e["carried_over"]:
            lines.append("**Repeatedly carried over**\n" + _bullets(e["carried_over"]))
        lines.append("**Blockers**\n" + _bullets(e["blockers"]))
        lines.append("")
    if r["decisions"]:
        lines.append("## Decisions")
        lines.extend(f"- {d['decision']} _({d['meeting']})_" for d in r["decisions"])
    return "\n\n".join(lines) + "\n"


def item_history(db: Session, item_id: str) -> List[Dict[str, Any]]:
    out = []
    for ev in db.scalars(select(WorkItemEvent).where(WorkItemEvent.work_item_id == item_id).order_by(WorkItemEvent.at)):
        m = db.get(Meeting, ev.meeting_id) if ev.meeting_id else None
        out.append({
            "kind": ev.kind, "from": ev.from_status, "to": ev.to_status, "note": ev.note, "actor": ev.actor,
            "at": ev.at, "meeting_id": ev.meeting_id, "meeting_title": m.title if m else None,
        })
    return out
