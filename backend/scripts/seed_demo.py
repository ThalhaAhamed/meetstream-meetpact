"""Load a demo workspace so the dashboards have something to show.

    python scripts/seed_demo.py            # adds demo data (refuses if users exist)
    python scripts/seed_demo.py --reset    # wipes the database first

No API keys are needed: the demo meetings are pushed through the same
tracker logic real meetings use, with the analysis written out by hand
instead of produced by Claude.

Logins (password for all: demo-password):
    admin@demo.local    admin
    maya@demo.local     manager
    priya@demo.local    employee (team lead of Platform)
    sam@demo.local      employee
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.db import Base, engine, init_db, session_scope  # noqa: E402
from app.models import (  # noqa: E402
    ConsentEvent, Employee, EmployeeProject, Meeting, MeetingParticipant, Project, Schedule, Team,
    TranscriptSegment, User,
)
from app.services import tracker  # noqa: E402
from app.services.extraction import (  # noqa: E402
    ActionItem, Commitment, EmployeeReport, ExistingItemUpdate, MeetingAnalysis, NewWorkItem,
)
from app.services.reports import render_meeting_report  # noqa: E402

PASSWORD = "demo-password"

PEOPLE = [
    # name, email, title, team, aliases
    ("Priya Raman", "priya@demo.local", "Senior Backend Engineer", "Platform", ["Priya R"]),
    ("Sam Okafor", "sam@demo.local", "Frontend Engineer", "Platform", ["Sam O", "samo-laptop"]),
    ("Lena Fischer", "lena@demo.local", "DevOps Engineer", "Platform", []),
    ("Diego Alvarez", "diego@demo.local", "Mobile Engineer", "Mobile", ["Diego A"]),
    ("Hana Sato", "hana@demo.local", "QA Engineer", "Mobile", []),
]

# Per workday (0 = oldest), slot -> person -> story.
# Keys: done, doing, plan, block, resolve (bool), due {title: days_from_day}
STORY = [
    {
        "morning": {
            "Priya Raman": {"plan": ["Build invoice export API", "Review billing schema migration"], "due": {"Build invoice export API": 3}},
            "Sam Okafor": {"plan": ["Implement invoice list page", "Fix date picker timezone bug"]},
            "Lena Fischer": {"plan": ["Set up staging database backups"]},
            "Diego Alvarez": {"plan": ["Add offline mode to mobile sync"], "due": {"Add offline mode to mobile sync": 5}},
            "Hana Sato": {"plan": ["Write regression suite for checkout"]},
        },
        "evening": {
            "Priya Raman": {"done": ["Review billing schema migration"], "doing": ["Build invoice export API"]},
            "Sam Okafor": {"done": ["Fix date picker timezone bug"], "doing": ["Implement invoice list page"]},
            "Lena Fischer": {"doing": ["Set up staging database backups"], "block": ["Waiting for cloud account access from IT"]},
            "Diego Alvarez": {"doing": ["Add offline mode to mobile sync"]},
            "Hana Sato": {"doing": ["Write regression suite for checkout"]},
        },
    },
    {
        "morning": {
            "Priya Raman": {"doing": ["Build invoice export API"], "plan": ["Add CSV formatting for exports"]},
            "Sam Okafor": {"doing": ["Implement invoice list page"]},
            "Lena Fischer": {"doing": ["Set up staging database backups"], "block": ["Waiting for cloud account access from IT"]},
            "Diego Alvarez": {"doing": ["Add offline mode to mobile sync"], "plan": ["Investigate crash on Android 14 login"]},
            "Hana Sato": {"doing": ["Write regression suite for checkout"]},
        },
        "evening": {
            "Priya Raman": {"done": ["Add CSV formatting for exports"], "doing": ["Build invoice export API"]},
            "Sam Okafor": {"doing": ["Implement invoice list page"], "block": ["Invoice API response shape not final"]},
            "Lena Fischer": {"resolve": True, "done": ["Set up staging database backups"]},
            "Diego Alvarez": {"done": ["Investigate crash on Android 14 login"], "doing": ["Add offline mode to mobile sync"]},
            "Hana Sato": {"done": ["Write regression suite for checkout"]},
        },
    },
    {
        "morning": {
            "Priya Raman": {"doing": ["Build invoice export API"], "plan": ["Document export API for frontend"], "due": {"Document export API for frontend": 0}},
            "Sam Okafor": {"doing": ["Implement invoice list page"], "block": ["Invoice API response shape not final"]},
            "Lena Fischer": {"plan": ["Add CPU alerts for API pods"]},
            "Diego Alvarez": {"doing": ["Add offline mode to mobile sync"]},
            "Hana Sato": {"plan": ["Test offline sync on low-end devices"]},
        },
        "evening": {
            "Priya Raman": {"done": ["Build invoice export API", "Document export API for frontend"]},
            "Sam Okafor": {"resolve": True, "doing": ["Implement invoice list page"]},
            "Lena Fischer": {"doing": ["Add CPU alerts for API pods"]},
            "Diego Alvarez": {"doing": ["Add offline mode to mobile sync"], "block": ["Sync conflicts when two devices edit the same record"]},
            "Hana Sato": {"doing": ["Test offline sync on low-end devices"]},
        },
    },
    {
        "morning": {
            "Priya Raman": {"plan": ["Rate-limit the public API"], "due": {"Rate-limit the public API": 4}},
            "Sam Okafor": {"doing": ["Implement invoice list page"], "plan": ["Add export button to invoice page"]},
            "Lena Fischer": {"doing": ["Add CPU alerts for API pods"]},
            "Diego Alvarez": {"doing": ["Add offline mode to mobile sync"], "block": ["Sync conflicts when two devices edit the same record"]},
            "Hana Sato": {"doing": ["Test offline sync on low-end devices"]},
        },
        "evening": {
            "Priya Raman": {"doing": ["Rate-limit the public API"]},
            "Sam Okafor": {"done": ["Implement invoice list page"], "doing": ["Add export button to invoice page"]},
            "Lena Fischer": {"done": ["Add CPU alerts for API pods"]},
            "Diego Alvarez": {"doing": ["Add offline mode to mobile sync"]},
            "Hana Sato": {"block": ["Test devices not delivered yet"]},
        },
    },
    {
        "morning": {
            "Priya Raman": {"doing": ["Rate-limit the public API"], "plan": ["Pair with Diego on sync conflict strategy"]},
            "Sam Okafor": {"doing": ["Add export button to invoice page"]},
            "Lena Fischer": {"plan": ["Rotate expiring TLS certificates"], "due": {"Rotate expiring TLS certificates": 1}},
            "Diego Alvarez": {"doing": ["Add offline mode to mobile sync"], "plan": ["Pair with Priya on sync conflicts"]},
            "Hana Sato": {"block": ["Test devices not delivered yet"], "plan": ["Write test plan for invoice export"]},
        },
        "evening": {},  # today's evening meeting has not happened yet
    },
]


def workdays(n: int) -> list[date]:
    days, d = [], date.today()
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


def line_for(name: str, story: dict, slot: str) -> str:
    first = name.split()[0]
    bits = []
    if story.get("done"):
        bits.append(("Yesterday I finished " if slot == "morning" else "Today I finished ") + "; ".join(story["done"]).lower() + ".")
    if story.get("doing"):
        bits.append("I'm still working on " + "; ".join(story["doing"]).lower() + ".")
    if story.get("plan"):
        bits.append(("Today I plan to " if slot == "morning" else "Next I'll ") + "; ".join(story["plan"]).lower() + ".")
    for t, d in (story.get("due") or {}).items():
        bits.append(f"Deadline for {t.lower()}: {'today' if not d else f'in {d} day' + ('s' if d != 1 else '')}.")
    if story.get("block"):
        bits.append("I'm blocked: " + "; ".join(story["block"]).lower() + ".")
    if story.get("resolve"):
        bits.append("The blocker from before is sorted now.")
    return " ".join(bits) or f"Nothing new from me, {first} here."


def build_analysis(db, meeting: Meeting, slot_story: dict, employees: dict) -> MeetingAnalysis:
    reports = []
    for name, story in slot_story.items():
        emp = employees[name]
        open_now = {w.title: w for w in tracker.open_items(db, emp.id)}
        existing, new = [], []
        for title in story.get("done", []):
            if title in open_now:
                existing.append(ExistingItemUpdate(work_item_id=open_now[title].id, new_status="completed", note="Reported as done", due_date=None))
            else:
                new.append(NewWorkItem(title=title, status="completed", due_date=None, project=None))
        for title in story.get("doing", []):
            if title in open_now:
                existing.append(ExistingItemUpdate(work_item_id=open_now[title].id, new_status="in_progress", note="Still in progress", due_date=None))
            else:
                new.append(NewWorkItem(title=title, status="in_progress", due_date=None, project=None))
        for title in story.get("plan", []):
            due = (story.get("due") or {}).get(title)
            due_s = (meeting.meeting_date + timedelta(days=due)).isoformat() if due is not None else None
            if title not in open_now:
                new.append(NewWorkItem(title=title, status="planned", due_date=due_s, project=None))
        resolved = [b.id for b in tracker.open_blockers(db, emp.id)] if story.get("resolve") else []
        pending = [t for t in open_now if t not in story.get("done", []) and slot_story is not None and meeting.slot == "evening"]
        reports.append(EmployeeReport(
            employee_id=emp.id, speaker_name=name,
            summary=line_for(name, story, meeting.slot),
            completed=story.get("done", []), in_progress=story.get("doing", []), planned=story.get("plan", []),
            pending=pending[:4], blockers=story.get("block", []),
            commitments=[Commitment(text=t, due_date=(meeting.meeting_date + timedelta(days=d)).isoformat())
                         for t, d in (story.get("due") or {}).items()],
            existing_item_updates=existing, new_work_items=new, resolved_blocker_ids=resolved,
        ))
    blockers = [b for s in slot_story.values() for b in s.get("block", [])]
    done = [d for s in slot_story.values() for d in s.get("done", [])]
    return MeetingAnalysis(
        overview=(f"{'Morning stand-up' if meeting.slot == 'morning' else 'Evening check-in'} with {len(slot_story)} people. "
                  + (f"Completed: {', '.join(done[:3])}. " if done else "")
                  + (f"Open blockers: {', '.join(blockers[:2])}." if blockers else "No new blockers.")),
        key_points=[f"{n.split()[0]}: {line_for(n, s, meeting.slot)[:120]}" for n, s in list(slot_story.items())[:4]],
        decisions=(["Ship invoice export behind a feature flag first"] if "Build invoice export API" in done else []),
        action_items=[ActionItem(title=f"Unblock: {b}", owner_name="Maya Chen", owner_employee_id=None, due_date=None) for b in blockers[:1]],
        open_questions=[],
        employee_reports=reports,
    )


def _backdate(db, m: Meeting, at: datetime) -> None:
    """Demo records happened in the past: stamp them with the meeting time."""
    from app.models import Blocker, EmployeeUpdate, WorkItem, WorkItemEvent

    later = at + timedelta(minutes=15)
    for w in db.scalars(select(WorkItem).where(WorkItem.created_meeting_id == m.id)):
        w.created_at = later
        w.updated_at = later
    for ev in db.scalars(select(WorkItemEvent).where(WorkItemEvent.meeting_id == m.id)):
        ev.at = later
        if ev.to_status == "completed":
            ev.work_item.completed_at = later
        ev.work_item.updated_at = later
    for w in db.scalars(select(WorkItem).where(WorkItem.created_meeting_id == m.id, WorkItem.status == "completed")):
        w.completed_at = w.completed_at if w.completed_at and w.completed_at.replace(tzinfo=timezone.utc) <= later else later
    for u in db.scalars(select(EmployeeUpdate).where(EmployeeUpdate.meeting_id == m.id)):
        u.created_at = later
    for b in db.scalars(select(Blocker).where(Blocker.raised_meeting_id == m.id)):
        b.created_at = later
    for b in db.scalars(select(Blocker).where(Blocker.resolved_meeting_id == m.id)):
        b.resolved_at = later
    db.flush()


def main(reset: bool) -> None:
    if reset:
        Base.metadata.drop_all(engine)
        from sqlalchemy import text

        with engine.begin() as conn:  # so migrations rebuild the schema from scratch
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    init_db()
    with session_scope() as db:
        if db.scalar(select(func.count(User.id))):
            print("The database already has users. Run with --reset to replace it with the demo.")
            return
        teams = {n: Team(name=n, description=d) for n, d in [("Platform", "Backend, web and infrastructure"), ("Mobile", "iOS and Android apps")]}
        db.add_all(teams.values())
        db.flush()
        projects = {
            "Billing revamp": Project(name="Billing revamp", description="Invoices, exports and payment flows", team_id=teams["Platform"].id, keywords=["invoice", "billing", "export", "csv"]),
            "Offline mobile": Project(name="Offline mobile", description="Offline-first sync for the mobile app", team_id=teams["Mobile"].id, keywords=["offline", "sync", "android", "mobile"]),
            "Reliability": Project(name="Reliability", description="Backups, alerting, certificates", team_id=teams["Platform"].id, keywords=["backup", "alert", "tls", "rate-limit", "certificates"]),
        }
        db.add_all(projects.values())
        db.flush()
        employees = {}
        for name, email, title, team, aliases in PEOPLE:
            e = Employee(name=name, email=email, title=title, team_id=teams[team].id, aliases=aliases)
            db.add(e)
            employees[name] = e
        maya = Employee(name="Maya Chen", email="maya@demo.local", title="Engineering Manager", aliases=[])
        db.add(maya)
        db.flush()
        teams["Platform"].lead_employee_id = employees["Priya Raman"].id
        for pname, members in [("Billing revamp", ["Priya Raman", "Sam Okafor"]), ("Offline mobile", ["Diego Alvarez", "Hana Sato"]),
                               ("Reliability", ["Lena Fischer", "Priya Raman"])]:
            for m in members:
                db.add(EmployeeProject(employee_id=employees[m].id, project_id=projects[pname].id))
        admin = User(email="admin@demo.local", name="Alex Admin", role="admin", password_hash=hash_password(PASSWORD))
        manager = User(email="maya@demo.local", name="Maya Chen", role="manager", password_hash=hash_password(PASSWORD), employee_id=maya.id)
        db.add_all([admin, manager,
                    User(email="priya@demo.local", name="Priya Raman", role="employee", password_hash=hash_password(PASSWORD), employee_id=employees["Priya Raman"].id),
                    User(email="sam@demo.local", name="Sam Okafor", role="employee", password_hash=hash_password(PASSWORD), employee_id=employees["Sam Okafor"].id)])
        db.flush()

        link = "https://meet.google.com/abc-defg-hij"
        share_full = {"audience": "participants", "user_ids": []}
        share_emp = {"audience": "managers", "user_ids": []}
        morning = Schedule(title="Morning stand-up", meeting_link=link, mode="standup", slot="morning", recurrence="weekdays",
                           time_of_day="09:30", timezone="UTC", start_date=date.today() - timedelta(days=14),
                           organizer_user_id=manager.id, share_full=share_full, share_employee=share_emp, active=False)
        evening = Schedule(title="Evening progress sync", meeting_link=link, mode="notetaker", slot="evening", recurrence="weekdays",
                           time_of_day="17:30", timezone="UTC", start_date=date.today() - timedelta(days=14),
                           organizer_user_id=manager.id, share_full=share_full, share_employee=share_emp, active=False)
        db.add_all([morning, evening])
        db.flush()

        for day, plan in zip(workdays(len(STORY)), STORY):
            for slot, sch, hour in (("morning", morning, 9), ("evening", evening, 17)):
                slot_story = plan.get(slot) or {}
                if not slot_story:
                    continue
                at = datetime.combine(day, time(hour, 30), tzinfo=timezone.utc)
                m = Meeting(
                    title=sch.title, meeting_link=link, mode=sch.mode, slot=slot, schedule_id=sch.id,
                    organizer_user_id=manager.id, scheduled_at=at, meeting_date=day, started_at=at,
                    ended_at=at + timedelta(minutes=18), bot_id=None, bot_status="ended", processing_status="analysing",
                    consent_notice_sent=True, share_full=share_full, share_employee=share_emp,
                    team_id=None, created_at=at,
                )
                db.add(m)
                db.flush()
                pos = 0
                for name in ["Maya Chen", *slot_story.keys()]:
                    shown = name if name != "Sam Okafor" else "samo-laptop"
                    emp = maya if name == "Maya Chen" else employees[name]
                    db.add(MeetingParticipant(meeting_id=m.id, display_name=shown, employee_id=emp.id, mapping="auto", notice_sent=True))
                db.add(MeetingParticipant(meeting_id=m.id, display_name="Progress Tracker AI Notetaker", is_bot=True, notice_sent=True))
                db.add(TranscriptSegment(meeting_id=m.id, position=pos, speaker="Maya Chen", employee_id=maya.id, start_seconds=0,
                                         text="Morning everyone, let's go round." if slot == "morning" else "Quick end-of-day check-in, let's go round."))
                for name, story in slot_story.items():
                    pos += 1
                    db.add(TranscriptSegment(meeting_id=m.id, position=pos, speaker=name if name != "Sam Okafor" else "samo-laptop",
                                             employee_id=employees[name].id, start_seconds=pos * 45.0, text=line_for(name, story, slot)))
                db.add(ConsentEvent(meeting_id=m.id, kind="notice_sent", detail="Recording notice posted in the meeting chat.", at=at + timedelta(seconds=20)))
                db.flush()
                db.refresh(m)
                analysis = build_analysis(db, m, slot_story, employees)
                stats = tracker.apply_analysis(db, m, analysis, set())
                data = analysis.model_dump()
                data["stats"] = stats
                m.summary = data
                m.processing_status = "done"
                db.flush()
                m.report_md = render_meeting_report(db, m)
                _backdate(db, m, at)
        # Attribute demo work items to projects by keyword.
        from app.models import WorkItem
        for w in db.scalars(select(WorkItem)):
            for p in projects.values():
                if any(k in w.title.lower() for k in p.keywords):
                    w.project_id = p.id
                    break
    print("Demo data loaded. Sign in with admin@demo.local / demo-password (or maya@, priya@, sam@).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop all tables first")
    main(ap.parse_args().reset)
