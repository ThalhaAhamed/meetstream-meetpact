"""Calendar auto-join, report delivery, search/ask, retention and erasure."""
import asyncio
from datetime import date, datetime, timedelta, timezone

from app.models import ConsentEvent, Employee, EmployeeUpdate, Meeting, MeetingParticipant, TranscriptSegment, WorkItem
from app.services.app_settings import set_settings
from app.services.meetstream import MeetStreamClient
from tests.conftest import login


def _event(minutes_from_now, title="Platform sync", url="https://meet.google.com/aaa-bbbb-ccc", eid="evt_1"):
    start = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    return {"id": eid, "start_time": start.isoformat(), "end_time": (start + timedelta(minutes=30)).isoformat(),
            "meeting_url": url, "meeting_platform": "google_meet", "is_deleted": False,
            "raw": {"summary": title, "organizer": {"email": "maya@t.local"}}, "bots": []}


def test_calendar_auto_join_books_matching_events_once(db, people, monkeypatch):
    from app.services import calendar_sync

    created = []

    async def events(self, max_pages=5):
        return [_event(5), _event(6, title="1:1 with Sam", eid="evt_2"), _event(7, url="", eid="evt_3"),
                _event(240, eid="evt_4")]

    async def create_bot(self, payload, idempotency_key=None):
        created.append(payload)
        return {"bot_id": f"bot_{len(created)}"}

    monkeypatch.setattr(MeetStreamClient, "calendar_events", events)
    monkeypatch.setattr(MeetStreamClient, "create_bot", create_bot)
    set_settings(db, {"calendar_connected": True, "calendar_auto_join": True, "calendar_exclude_keywords": ["1:1"]})
    assert asyncio.run(calendar_sync.sweep(db)) == 1  # 1:1 excluded, no link skipped, 4h away not yet
    assert asyncio.run(calendar_sync.sweep(db)) == 0  # not booked twice
    m = db.query(Meeting).filter(Meeting.occurrence_key.like("cal:evt_1:%")).one()
    assert m.title == "Platform sync" and m.bot_id == "bot_1" and "join_at" in created[0]


def test_calendar_off_books_nothing(db, monkeypatch):
    from app.services import calendar_sync

    set_settings(db, {"calendar_connected": True, "calendar_auto_join": False})
    assert asyncio.run(calendar_sync.sweep(db)) == 0


def _done_meeting(db, people, audience="participants"):
    e = people["emps"]
    m = Meeting(title="Billing sync", processing_status="done", organizer_user_id=people["users"]["mgr"].id,
                share_full={"audience": audience}, share_employee={"audience": "managers"},
                summary={"overview": "We shipped export.", "decisions": ["Ship behind a flag"],
                         "action_items": [{"title": "Write docs", "owner_name": "Priya Raman", "due_date": None}]})
    db.add(m)
    db.flush()
    for k in ("sam", "lena"):
        db.add(MeetingParticipant(meeting_id=m.id, display_name=e[k].name, employee_id=e[k].id))
        db.add(EmployeeUpdate(meeting_id=m.id, employee_id=e[k].id, summary=f"{k} private update"))
    db.commit()
    return m


def test_delivery_respects_sharing_and_sends_once(db, people, monkeypatch):
    from app.config import settings
    from app.services import delivery

    sent, posted = [], []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "SMTP_FROM", "notes@t.local")
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.setattr(delivery, "_send_email", lambda to, subject, body: sent.append((to, body)))

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json):
            posted.append(json["text"])
            class R: status_code = 200
            return R()

    monkeypatch.setattr(delivery.httpx, "AsyncClient", FakeClient)
    set_settings(db, {"deliver_email": True, "deliver_slack": True})
    m = _done_meeting(db, people)
    result = asyncio.run(delivery.deliver(db, m))
    to = {t for t, _ in sent}
    # Organizer (mgr), admin and the two participants; not the lead who wasn't there.
    assert to == {"mgr@t.local", "admin@t.local", "sam@t.local", "lena@t.local"}
    sam_body = next(b for t, b in sent if t == "sam@t.local")
    assert "sam private update" in sam_body and "lena private update" not in sam_body
    assert result["slack"] == 1 and "Ship behind a flag" in posted[0]
    assert asyncio.run(delivery.deliver(db, m)) == {"emails": 0, "slack": 0}  # once only


def test_slack_skipped_for_organizer_only_reports(db, people, monkeypatch):
    from app.config import settings
    from app.services import delivery

    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    set_settings(db, {"deliver_slack": True})
    m = _done_meeting(db, people, audience="organizer")
    assert asyncio.run(delivery.deliver(db, m))["slack"] == 0


def test_search_and_ask_only_use_visible_records(client, db, people, monkeypatch):
    e = people["emps"]
    m = _done_meeting(db, people, audience="organizer")
    db.add(WorkItem(employee_id=e["lena"].id, title="Rotate TLS certificates", status="planned"))
    db.add(WorkItem(employee_id=e["sam"].id, title="Rotate invoice page colours", status="planned"))
    db.commit()
    login(client, "sam")
    r = client.get("/api/search", params={"q": "rotate"}).json()
    assert [w["title"] for w in r["work_items"]] == ["Rotate invoice page colours"]
    assert r["meetings"] == [] or all(x["overview"] is None for x in r["meetings"])

    seen = {}

    async def fake_complete(system, prompt, max_tokens=4000):
        seen["prompt"] = prompt
        return "Sam plans to rotate invoice page colours (Billing sync)."

    monkeypatch.setattr("app.services.knowledge.complete_text", fake_complete)
    r = client.post("/api/ask", json={"question": "What is Sam rotating?"}).json()
    assert "invoice page colours" in r["answer"]
    assert "TLS" not in seen["prompt"] and "lena private update" not in seen["prompt"]


def test_delete_recording_and_retention(db, people, monkeypatch):
    from app.services import retention

    deleted = []

    async def delete_bot_data(self, bot_id):
        deleted.append(bot_id)
        return {}

    monkeypatch.setattr(MeetStreamClient, "delete_bot_data", delete_bot_data)
    old = Meeting(title="Old", bot_id="bot_old", processing_status="done",
                  created_at=datetime.now(timezone.utc) - timedelta(days=40))
    new = Meeting(title="New", bot_id="bot_new", processing_status="done")
    db.add_all([old, new])
    db.flush()
    db.add(TranscriptSegment(meeting_id=old.id, position=0, speaker="A", text="secret"))
    db.commit()
    set_settings(db, {"transcript_retention_days": 30})
    assert asyncio.run(retention.purge_expired(db)) == 1
    db.refresh(old)
    assert deleted == ["bot_old"] and old.media_deleted_at and not old.segments
    assert db.query(ConsentEvent).filter_by(meeting_id=old.id, kind="data_deleted").count() == 1
    assert asyncio.run(retention.purge_expired(db)) == 0  # not twice


def test_erase_employee_is_admin_only_and_complete(client, db, people):
    e = people["emps"]
    m = _done_meeting(db, people)
    db.add(TranscriptSegment(meeting_id=m.id, position=0, speaker="Sam Okafor", employee_id=e["sam"].id, text="my stuff"))
    db.add(WorkItem(employee_id=e["sam"].id, title="Sam's task", status="planned"))
    db.commit()
    sam_id = e["sam"].id
    login(client, "mgr")
    assert client.post(f"/api/employees/{sam_id}/erase").status_code == 403
    login(client, "admin")
    r = client.post(f"/api/employees/{sam_id}/erase").json()
    assert r["updates"] == 1 and r["work_items"] == 1 and r["transcript_lines"] == 1
    db.expire_all()
    assert db.get(Employee, sam_id) is None
    seg = db.query(TranscriptSegment).filter_by(meeting_id=m.id).one()
    assert seg.text == "[removed]" and seg.speaker == "Removed person"


def test_google_calendar_sign_in(client, db, people, monkeypatch):
    """Connect Google Calendar: start -> Google -> callback -> token to MeetStream."""
    from urllib.parse import parse_qs, urlparse

    import httpx

    from app.config import settings

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(settings, "APP_URL", "http://localhost:5173")
    sent = {}

    async def connect_google(self, client_id, client_secret, refresh_token):
        sent.update(client_id=client_id, refresh_token=refresh_token)
        return {"user_email": "owner@example.com"}

    class FakeResp:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return {"access_token": "a", "refresh_token": "r-123"}

    async def fake_post(self, url, data=None, **kw):
        assert url == "https://oauth2.googleapis.com/token" and data["code"] == "the-code"
        return FakeResp()

    monkeypatch.setattr(MeetStreamClient, "connect_google_calendar", connect_google)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    login(client, "admin")
    assert client.get("/api/calendar").json()["google_sign_in"] is True
    r = client.get("/api/calendar/google/start", follow_redirects=False)
    assert r.status_code == 303
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["access_type"] == ["offline"] and "calendar.readonly" in q["scope"][0]
    assert q["redirect_uri"] == [f"http://localhost:{settings.PORT}/api/calendar/google/callback"]

    bad = client.get("/api/calendar/google/callback", params={"code": "the-code", "state": "forged"}, follow_redirects=False)
    assert "calendar_error" in bad.headers["location"] and not sent

    ok = client.get("/api/calendar/google/callback", params={"code": "the-code", "state": q["state"][0]}, follow_redirects=False)
    assert ok.headers["location"] == "http://localhost:5173/schedules?calendar=connected"
    assert sent == {"client_id": "cid.apps.googleusercontent.com", "refresh_token": "r-123"}
    assert client.get("/api/calendar").json()["account"] == "owner@example.com"

    login(client, "mgr")
    assert client.get("/api/calendar/google/start", follow_redirects=False).status_code == 403
