"""Search and ask across meetings, limited to what the asking user may see."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import access
from app.api import serializers as S
from app.models import Blocker, EmployeeUpdate, Meeting, TranscriptSegment, User, WorkItem
from app.services.extraction import complete_text

_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "what", "did", "does", "is", "are", "was",
         "were", "who", "when", "how", "about", "with", "last", "this", "that", "week", "today", "yesterday", "any",
         "has", "have", "do", "me", "tell", "show", "list", "it", "be", "by", "at"}


def terms(q: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9\-']+", q.lower()) if w not in _STOP][:8]


def search(db: Session, user: User, q: str, limit: int = 30) -> Dict[str, List[Dict[str, Any]]]:
    words = terms(q)
    out: Dict[str, List[Dict[str, Any]]] = {"meetings": [], "updates": [], "work_items": [], "transcript": []}
    if not words:
        return out
    visible = access.visible_employee_ids(db, user)

    def like_any(col):
        return or_(*[col.ilike(f"%{w}%") for w in words])

    for m in db.scalars(select(Meeting).options(selectinload(Meeting.participants))
                        .where(like_any(Meeting.title) | like_any(Meeting.report_md))
                        .order_by(Meeting.created_at.desc()).limit(limit)):
        if access.can_view_meeting_at_all(db, user, m):
            d = S.meeting_brief(m)
            if not access.can_view_full(db, user, m):
                d["overview"] = None
            out["meetings"].append(d)

    for u in db.scalars(select(EmployeeUpdate).where(like_any(EmployeeUpdate.summary))
                        .order_by(EmployeeUpdate.created_at.desc()).limit(limit * 2)):
        if access.can_view_employee_section(db, user, u.meeting, u.employee_id):
            out["updates"].append(S.update(u))
    out["updates"] = out["updates"][:limit]

    for w in db.scalars(select(WorkItem).where(like_any(WorkItem.title) | like_any(WorkItem.details))
                        .order_by(WorkItem.updated_at.desc()).limit(limit * 2)):
        if (visible is None) or (w.employee_id in visible) or (w.employee_id is None and access.is_manager(user)):
            out["work_items"].append(S.work_item(w))
    out["work_items"] = out["work_items"][:limit]

    for seg in db.scalars(select(TranscriptSegment).where(like_any(TranscriptSegment.text),
                                                          TranscriptSegment.redacted.is_(False))
                          .order_by(TranscriptSegment.meeting_id).limit(limit * 3)):
        m = seg.meeting
        if access.can_view_full(db, user, m):
            out["transcript"].append({"meeting_id": m.id, "meeting_title": m.title, "speaker": seg.speaker,
                                      "text": seg.text[:400], "start": seg.start_seconds,
                                      "date": S.iso(m.meeting_date or m.created_at)})
    out["transcript"] = out["transcript"][:limit]
    return out


ASK_SYSTEM = """You answer questions about a team's work, using ONLY the meeting records provided.
- Cite the meeting and date for each fact, e.g. "(Stand-up, 2026-11-14)".
- If the records do not contain the answer, say so plainly. Never guess.
- Refer to people by name; use "they" when a pronoun is needed.
- Be brief: a few sentences or a short list."""


def _current_state(db: Session, user: User) -> List[str]:
    """Open blockers and open work the user may see - so questions like
    'what is blocking the team' are answered from the full current picture,
    not only from keyword hits."""
    visible = access.visible_employee_ids(db, user)
    ok = lambda emp_id: visible is None or emp_id in visible  # noqa: E731
    lines = []
    for b in db.scalars(select(Blocker).where(Blocker.status == "open").order_by(Blocker.created_at)):
        if b.employee_id and ok(b.employee_id):
            lines.append(f"[Open blocker] {b.employee.name if b.employee else '?'}: {b.description} "
                         f"(raised {b.created_at:%Y-%m-%d}, mentioned in {b.mention_count} meeting(s))")
    open_items = db.scalars(select(WorkItem).where(WorkItem.status.in_(["planned", "in_progress", "blocked"]))
                            .order_by(WorkItem.due_date.is_(None), WorkItem.due_date, WorkItem.updated_at.desc()))
    n = 0
    for w in open_items:
        if w.employee_id and ok(w.employee_id):
            lines.append(f"[Open work] {w.employee.name if w.employee else '?'}: {w.title} - {w.status}"
                         f"{' - due ' + w.due_date.isoformat() if w.due_date else ''}"
                         f"{' - carried over ' + str(w.carry_count) + 'x' if w.carry_count else ''}")
            n += 1
            if n >= 40:
                break
    return lines


def _context(db: Session, user: User, question: str) -> str:
    found = search(db, user, question, limit=15)
    lines: List[str] = _current_state(db, user)
    for u in found["updates"]:
        lines.append(f"[Update] {u['employee_name']} in '{u['meeting_title']}' on {u['meeting_date']}: {u['summary']} "
                     f"| done: {u['completed']} | in progress: {u['in_progress']} | planned: {u['planned']} "
                     f"| blockers: {u['blockers']} | commitments: {u['commitments']}")
    for w in found["work_items"]:
        lines.append(f"[Work item] {w['title']} - {w['employee_name'] or 'unassigned'} - status {w['status']}"
                     f"{' - due ' + w['due_date'] if w['due_date'] else ''} - carried over {w['carry_count']}x")
    for t in found["transcript"]:
        lines.append(f"[Transcript] '{t['meeting_title']}' {t['date']} - {t['speaker']}: {t['text']}")
    for m in found["meetings"]:
        if m.get("overview"):
            lines.append(f"[Meeting] '{m['title']}' {m['meeting_date']}: {m['overview']}")
    if len(found["updates"]) + len(found["transcript"]) < 3:  # vague question: add recent updates too
        recent = db.scalars(select(EmployeeUpdate).order_by(EmployeeUpdate.created_at.desc()).limit(40))
        for u in recent:
            if access.can_view_employee_section(db, user, u.meeting, u.employee_id):
                lines.append(f"[Update] {u.employee.name} in '{u.meeting.title}' on {u.meeting_date}: {u.summary}")
            if len(lines) >= 25:
                break
    return "\n".join(lines[:80])


async def ask(db: Session, user: User, question: str) -> Dict[str, Any]:
    ctx = _context(db, user, question)
    if not ctx:
        return {"answer": "There are no meeting records you can see yet.", "sources": 0}
    prompt = f"Today is {date.today().isoformat()}.\n\n<records>\n{ctx}\n</records>\n\nQuestion: {question}"
    answer = await complete_text(ASK_SYSTEM, prompt, max_tokens=1500)
    return {"answer": answer, "sources": ctx.count("\n") + 1}
