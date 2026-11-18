"""End-to-end flows with MeetStream and Claude mocked."""
import asyncio
from datetime import date

import pytest

from app.models import EmployeeUpdate, Meeting, WorkItem
from app.services import tracker
from app.services.extraction import EmployeeReport, ExistingItemUpdate, MeetingAnalysis, NewWorkItem
from app.services.meetstream import MeetStreamClient
from tests.conftest import login


def _report(emp, **kw):
    base = dict(employee_id=emp.id, speaker_name=emp.name, summary="s", completed=[], in_progress=[], planned=[],
                pending=[], blockers=[], commitments=[], existing_item_updates=[], new_work_items=[], resolved_blocker_ids=[])
    base.update(kw)
    return EmployeeReport(**base)


def _analysis(*reports):
    return MeetingAnalysis(overview="o", key_points=[], decisions=[], action_items=[], open_questions=[], employee_reports=list(reports))


def _meeting(db, slot, day=date(2026, 11, 16)):
    m = Meeting(title=f"{slot} sync", slot=slot, meeting_date=day, processing_status="analysing")
    db.add(m)
    db.commit()
    return m


def test_plan_then_outcome_and_carry_over(db, people):
    priya = people["emps"]["lead"]
    m1 = _meeting(db, "morning")
    tracker.apply_analysis(db, m1, _analysis(_report(priya, planned=["Build export API", "Write docs"], new_work_items=[
        NewWorkItem(title="Build export API", status="planned", due_date="2026-11-18", project=None),
        NewWorkItem(title="Write docs", status="planned", due_date=None, project=None),
    ])))
    db.commit()
    items = {w.title: w for w in tracker.open_items(db, priya.id)}
    assert set(items) == {"Build export API", "Write docs"}

    # Evening: export done; docs not mentioned -> carried over.
    m2 = _meeting(db, "evening")
    stats = tracker.apply_analysis(db, m2, _analysis(_report(priya, completed=["Build export API"], existing_item_updates=[
        ExistingItemUpdate(work_item_id=items["Build export API"].id, new_status="completed", note="done", due_date=None)
    ], blockers=["Waiting on design review"])))
    db.commit()
    assert stats["carried_over"] == 1 and stats["blockers"] == 1
    assert db.get(WorkItem, items["Build export API"].id).status == "completed"
    docs = db.get(WorkItem, items["Write docs"].id)
    assert docs.carry_count == 1 and [e.kind for e in docs.events] == ["created", "carried_over"]

    # Re-processing the same meeting must not double count.
    stats = tracker.apply_analysis(db, m2, _analysis(_report(priya)))
    db.commit()
    assert db.get(WorkItem, docs.id).carry_count == 1
    assert db.query(EmployeeUpdate).filter_by(meeting_id=m2.id).count() == 1


def test_duplicate_new_items_are_merged(db, people):
    sam, lena = people["emps"]["sam"], people["emps"]["lena"]
    m = _meeting(db, "general")
    tracker.apply_analysis(db, m, _analysis(
        _report(sam, new_work_items=[NewWorkItem(title="Fix date picker bug", status="in_progress", due_date=None, project=None)]),
    ))
    m2 = _meeting(db, "general")
    tracker.apply_analysis(db, m2, _analysis(
        _report(sam, new_work_items=[NewWorkItem(title="Fix the date-picker bug", status="completed", due_date=None, project=None)]),
    ))
    db.commit()
    sam_items = db.query(WorkItem).filter_by(employee_id=sam.id).all()
    assert len(sam_items) == 1 and sam_items[0].status == "completed"
    assert db.query(WorkItem).filter_by(employee_id=lena.id).count() == 0


def test_access_rules(client, db, people):
    e = people["emps"]
    m = Meeting(title="Sync", processing_status="done", organizer_user_id=people["users"]["mgr"].id,
                share_full={"audience": "organizer"}, share_employee={"audience": "managers"})
    db.add(m)
    db.flush()
    from app.models import MeetingParticipant

    for k in ("sam", "lena"):
        db.add(MeetingParticipant(meeting_id=m.id, display_name=e[k].name, employee_id=e[k].id))
        db.add(EmployeeUpdate(meeting_id=m.id, employee_id=e[k].id, summary=f"{k} update"))
    db.commit()

    login(client, "sam")
    d = client.get(f"/api/meetings/{m.id}").json()
    assert d["permissions"]["full"] is False and d["summary"] is None
    assert [u["employee_id"] for u in d["updates"]] == [e["sam"].id]  # only his own
    assert client.get(f"/api/meetings/{m.id}/report.md").status_code == 403
    assert client.get(f"/api/employees/{e['lena'].id}/profile").status_code == 403

    login(client, "lead")  # team lead of sam & lena
    d = client.get(f"/api/meetings/{m.id}").json()
    assert len(d["updates"]) == 2 and d["permissions"]["full"] is False
    assert client.get(f"/api/employees/{e['lena'].id}/profile").status_code == 200

    login(client, "mgr")  # organizer
    assert client.get(f"/api/meetings/{m.id}").json()["permissions"]["full"] is True
    # The organizer opens the full report to participants.
    r = client.put(f"/api/meetings/{m.id}/share", json={"share_full": {"audience": "participants"}, "share_employee": {"audience": "selected", "user_ids": []}})
    assert r.status_code == 200
    login(client, "sam")
    d = client.get(f"/api/meetings/{m.id}").json()
    assert d["permissions"]["full"] is True and [u["employee_id"] for u in d["updates"]] == [e["sam"].id]


def test_employee_review_and_correction(client, db, people):
    e = people["emps"]
    m = _meeting(db, "morning")
    tracker.apply_analysis(db, m, _analysis(_report(e["sam"], new_work_items=[
        NewWorkItem(title="Wrong title", status="planned", due_date=None, project=None)])))
    db.commit()
    item = db.query(WorkItem).filter_by(employee_id=e["sam"].id).one()
    upd = db.query(EmployeeUpdate).filter_by(employee_id=e["sam"].id).one()
    login(client, "sam")
    r = client.patch(f"/api/work-items/{item.id}", json={"title": "Right title", "status": "in_progress", "note": "AI misheard"})
    assert r.status_code == 200 and r.json()["title"] == "Right title"
    hist = client.get(f"/api/work-items/{item.id}").json()["history"]
    assert [h["kind"] for h in hist] == ["created", "corrected", "status_changed"]
    r = client.patch(f"/api/updates/{upd.id}", json={"review_status": "corrected", "employee_note": "fixed", "planned": ["Right title"]})
    assert r.json()["review_status"] == "corrected"
    login(client, "lena")
    assert client.patch(f"/api/work-items/{item.id}", json={"status": "completed"}).status_code == 403


def test_launch_payload_and_consent_flow(client, db, people, monkeypatch):
    sent, created = [], {}

    async def create_bot(self, payload, idempotency_key=None):
        created.update(payload)
        return {"bot_id": "bot_1", "transcript_id": "tr_1"}

    async def status(self, bot_id):
        return "InMeeting"

    async def participants(self, bot_id):
        return [{"displayName": "Priya Raman"}, {"displayName": "MeetPact AI Notetaker"}]

    async def chats(self, bot_id):
        return []

    async def send_message(self, bot_id, message):
        sent.append(message)
        return {}

    for name, fn in dict(create_bot=create_bot, status=status, participants=participants, chats=chats, send_message=send_message).items():
        monkeypatch.setattr(MeetStreamClient, name, fn)

    login(client, "mgr")
    r = client.post("/api/meetings", json={"title": "Sync", "meeting_link": "https://meet.google.com/abc-defg-hij"})
    assert r.status_code == 200, r.text
    assert created["video_required"] is False and created["custom_attributes"]["meeting_id"] == r.json()["id"]
    assert "callback_url" not in created  # no PUBLIC_URL -> polling mode

    from app.services.workers import watch_sweep

    asyncio.run(watch_sweep())
    assert len(sent) == 1 and "recorded" in sent[0]  # notice after admission

    async def participants2(self, bot_id):
        return [{"displayName": "Priya Raman"}, {"displayName": "Sam Okafor"}]

    monkeypatch.setattr(MeetStreamClient, "participants", participants2)
    asyncio.run(watch_sweep())
    assert len(sent) == 1  # one notice only, no per-person messages
    d = client.get(f"/api/meetings/{r.json()['id']}").json()
    assert [e["kind"] for e in d["consent_events"]] == ["notice_sent"]
    assert {p["display_name"] for p in d["participants"]} >= {"Priya Raman", "Sam Okafor"}


def test_unassigned_item_hidden_from_employees(client, db, people):
    item = tracker.create_item(db, employee_id=None, title="Secret action", status="planned", meeting=None)
    db.commit()
    login(client, "sam")
    assert client.get(f"/api/work-items/{item.id}").status_code == 404
    login(client, "mgr")
    assert client.get(f"/api/work-items/{item.id}").status_code == 200


def test_post_call_pipeline(client, db, people, monkeypatch):
    async def get_transcript(self, tid):
        return [{"speaker": "Priya Raman", "transcript": "I shipped the export."}, {"speaker": "Sam Okafor", "transcript": "Private stuff."}]

    async def fake_analyse(prompt):
        assert "Private stuff" in prompt and "I shipped the export" in prompt
        p = people["emps"]["lead"]
        return _analysis(_report(p, completed=["Ship export"], new_work_items=[NewWorkItem(title="Ship export", status="completed", due_date=None, project=None)]))

    monkeypatch.setattr(MeetStreamClient, "get_transcript", get_transcript)
    monkeypatch.setattr("app.services.processing.analyse_meeting", fake_analyse)

    m = Meeting(title="Sync", bot_id="bot_9", transcript_id="tr_9", bot_status="ended", processing_status="waiting", meeting_date=date.today())
    db.add(m)
    db.commit()
    from app.services.processing import process_meeting

    assert asyncio.run(process_meeting(m.id)) == "done"
    db.expire_all()
    m = db.get(Meeting, m.id)
    assert len(m.segments) == 2
    assert "Ship export" in m.report_md


def test_webhook_dedupe_and_stop(client, db, monkeypatch):
    m = Meeting(title="W", bot_id="bot_w", bot_status="recording")
    db.add(m)
    db.commit()
    body = {"event": "bot.stopped", "bot_event": "bot.denied", "bot_id": "bot_w", "timestamp": "2026-11-17T10:00:00Z", "status_code": 500}
    assert client.post("/api/webhooks/meetstream", json=body).json() == {"ok": True}
    assert client.post("/api/webhooks/meetstream", json=body).json()["duplicate"] is True
    import time

    for _ in range(20):
        db.expire_all()
        if db.get(Meeting, m.id).bot_status == "denied":
            break
        time.sleep(0.05)
    m = db.get(Meeting, m.id)
    assert m.bot_status == "denied" and m.processing_status == "skipped"


def test_mcp_requires_token(client, db):
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
    from app.services.app_settings import set_settings

    set_settings(db, {"mcp_token": "tok"})
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"Authorization": "Bearer tok"})
    assert {t["name"] for t in r.json()["result"]["tools"]} == {"get_person_context", "list_standup_roster"}


def test_late_added_employee_is_linked_on_reanalysis(db, people, monkeypatch):
    """Live test: the speaker was seen before their employee profile existed,
    so the meeting stayed 'unmatched' even after the profile was created."""
    from app.models import Employee, MeetingParticipant, TranscriptSegment
    from app.services.processing import rematch_participants

    m = Meeting(title="L", processing_status="done")
    db.add(m)
    db.flush()
    db.add(MeetingParticipant(meeting_id=m.id, display_name="Noor Haddad", mapping="unmatched"))
    db.add(TranscriptSegment(meeting_id=m.id, position=0, speaker="Noor Haddad", text="hi"))
    db.commit()
    emp = Employee(name="Noor Haddad")
    db.add(emp)
    db.commit()
    db.refresh(m)
    rematch_participants(db, m)
    assert m.participants[0].employee_id == emp.id and m.segments[0].employee_id == emp.id


def test_work_listed_only_in_update_lists_is_tracked(db, people):
    """Live test: Gemini put work in in_progress/planned but left new_work_items
    empty, so nothing was tracked."""
    sam = people["emps"]["sam"]
    m = _meeting(db, "general")
    stats = tracker.apply_analysis(db, m, _analysis(_report(sam, in_progress=["Finish invoice page"],
                                                            planned=["Fix slow API response time"])))
    db.commit()
    items = {w.title: w.status for w in db.query(WorkItem).filter_by(employee_id=sam.id)}
    assert items == {"Finish invoice page": "in_progress", "Fix slow API response time": "planned"}
    assert stats["items_created"] == 2
    # Listed again next meeting as completed -> same item, not a duplicate.
    m2 = _meeting(db, "general")
    tracker.apply_analysis(db, m2, _analysis(_report(sam, completed=["Finish invoice page"])))
    db.commit()
    items = {w.title: w.status for w in db.query(WorkItem).filter_by(employee_id=sam.id)}
    assert items["Finish invoice page"] == "completed" and len(items) == 2


def test_commitment_already_applied_as_deadline_is_not_duplicated(db, people):
    """Live test 2: 'done this evening' set the deadline on the existing item AND
    became a separate commitment item."""
    sam = people["emps"]["sam"]
    m1 = _meeting(db, "general")
    tracker.apply_analysis(db, m1, _analysis(_report(sam, new_work_items=[
        NewWorkItem(title="Finish the invoice page", status="in_progress", due_date=None, project=None)])))
    db.commit()
    item = db.query(WorkItem).filter_by(employee_id=sam.id).one()
    from app.services.extraction import Commitment

    m2 = _meeting(db, "general")
    tracker.apply_analysis(db, m2, _analysis(_report(
        sam, existing_item_updates=[ExistingItemUpdate(work_item_id=item.id, new_status="unchanged", note="n", due_date="2026-11-18")],
        commitments=[Commitment(text="Will be done with it this evening", due_date="2026-11-18")])))
    db.commit()
    items = db.query(WorkItem).filter_by(employee_id=sam.id).all()
    assert len(items) == 1 and str(items[0].due_date) == "2026-11-18"


def test_vague_update_lines_do_not_become_items(db, people):
    """Live stand-up test: 'Finish the current task today' became its own work item."""
    sam = people["emps"]["sam"]
    m = _meeting(db, "general")
    tracker.apply_analysis(db, m, _analysis(_report(sam, planned=["Finish the current task today", "Write the export API docs"])))
    db.commit()
    assert [w.title for w in db.query(WorkItem).filter_by(employee_id=sam.id)] == ["Write the export API docs"]


def test_standup_prompt_asks_consent_once_and_stops():
    from app.models import Meeting
    from app.db import SessionLocal
    from app.services import standup

    db = SessionLocal()
    prompt = standup.system_prompt(db, Meeting(title="s", mode="standup"), can_leave=False)
    assert "do not ask about recording" in prompt and "anything else" in prompt and "leave the meeting now" in prompt
    assert "stay completely silent" in prompt


def test_standup_runs_start_to_finish_and_can_leave(client, db, people, monkeypatch):
    """The agent opens, goes round, asks for anything else, closes and leaves:
    with PUBLIC_URL via the end_meeting tool, otherwise via a silence timeout."""
    from app.config import settings
    from app.services import bots, standup
    from app.services.app_settings import set_settings

    m = Meeting(title="Daily", mode="standup", meeting_link="https://meet.google.com/x", team_id=people["team"].id)
    db.add(m)
    db.commit()
    # No public URL: no tool, silence timeout on the bot instead.
    p = standup.agent_payload(db, m, None)
    assert p["agent"]["custom_functions"] == [] and p["agent"]["response_type"] == "voice"
    assert bots.build_payload(db, m, None)["automatic_leave"]["voice_inactivity_timeout"] == settings.STANDUP_SILENCE_LEAVE_SECONDS
    # With a public URL the agent gets the leave tool.
    monkeypatch.setattr(settings, "PUBLIC_URL", "https://tracker.example.com")
    p = standup.agent_payload(db, m, "tok")
    fn = next(f for f in p["agent"]["custom_functions"] if f["name"] == "end_meeting")
    assert fn["url"] == "https://tracker.example.com/api/agent/leave"
    assert p["agent"]["response_type"] == "action" and "end_meeting tool" in p["model"]["system_prompt"]

    # The leave endpoint: auth required, only for live stand-up bots.
    removed = []

    async def remove_bot(self, bot_id):
        removed.append(bot_id)
        return {}

    monkeypatch.setattr(MeetStreamClient, "remove_bot", remove_bot)
    monkeypatch.setattr("app.api.agent.LEAVE_DELAY_SECONDS", 0)
    set_settings(db, {"mcp_token": "tok"})
    m.bot_id, m.bot_status = "bot_su", "in_meeting"
    db.commit()
    body = {"name": "end_meeting", "bot": {"bot_id": "bot_su"}, "args": {"reason": "done"}}
    assert client.post("/api/agent/leave", json=body).status_code == 401
    r = client.post("/api/agent/leave", json=body, headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    import time
    for _ in range(40):
        if removed:
            break
        time.sleep(0.05)
    assert removed == ["bot_su"]
    assert client.post("/api/agent/leave", json={"bot": {"bot_id": "nope"}}, headers={"Authorization": "Bearer tok"}).status_code == 404


def test_agent_sees_live_participants_from_webhooks(client, db, people, monkeypatch):
    """With PUBLIC_URL, join/leave webhooks tell the stand-up agent who is in the call now."""
    from app.config import settings
    from app.services import standup
    from app.services.app_settings import set_settings

    async def send_message(self, bot_id, message):
        return {}

    monkeypatch.setattr(MeetStreamClient, "send_message", send_message)
    set_settings(db, {"mcp_token": "tok"})
    m = Meeting(title="Daily", mode="standup", bot_id="bot_lp", bot_status="in_meeting", consent_notice_sent=True)
    db.add(m)
    db.commit()
    monkeypatch.setattr(settings, "PUBLIC_URL", "https://x.example.com")
    names = [f["name"] for f in standup.agent_payload(db, m, "tok")["agent"]["custom_functions"]]
    assert names == ["list_participants_now", "end_meeting"]

    def event(action, name, ts):
        return {"event": f"participant_events.{action}", "timestamp": ts,
                "data": {"data": {"action": action, "participant": {"id": name, "name": name}}, "bot": {"id": "bot_lp"}}}

    import time
    hdr = {"Authorization": "Bearer tok"}
    call = {"name": "list_participants_now", "bot": {"bot_id": "bot_lp"}, "args": {}}
    client.post("/api/webhooks/participants", json=event("join", "Sam Okafor", "t1"))
    client.post("/api/webhooks/participants", json=event("join", "Lena Fischer", "t2"))
    client.post("/api/webhooks/participants", json=event("leave", "Lena Fischer", "t3"))
    for _ in range(40):
        r = client.post("/api/agent/participants", json=call, headers=hdr).json()["result"]
        if "Left the call: Lena Fischer" in r:
            break
        time.sleep(0.05)
    assert r.startswith("Joined since you arrived: Sam Okafor. Left the call: Lena Fischer.")
    assert "never mention" in r
    assert client.post("/api/agent/participants", json=call).status_code == 401
