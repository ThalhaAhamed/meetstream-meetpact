from datetime import date, datetime, timedelta, timezone

from app.models import Employee, Schedule
from app.services import identity, recurrence
from app.services.consent import normalize_chats, roster_names
from app.services.meetstream import map_remote_status, stop_reason
from app.services.transcript import normalize_transcript, parse_plain_transcript


def _sched(**kw):
    base = dict(title="s", meeting_link="x", recurrence="weekdays", days_of_week=[], time_of_day="09:30",
                timezone="UTC", start_date=date(2026, 11, 2))
    base.update(kw)
    return Schedule(**base)


def test_weekdays_skip_weekend():
    s = _sched()
    start = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)  # Friday
    got = list(recurrence.occurrences(s, start, start + timedelta(days=5)))
    assert [t.weekday() for t in got] == [4, 0, 1]  # Fri, Mon, Tue


def test_weekly_days_and_timezone():
    s = _sched(recurrence="weekly", days_of_week=[0, 2], timezone="Asia/Kolkata", time_of_day="09:00")
    start = datetime(2026, 11, 9, tzinfo=timezone.utc)
    got = list(recurrence.occurrences(s, start, start + timedelta(days=7)))
    assert len(got) == 2
    assert got[0].hour == 3 and got[0].minute == 30  # 09:00 IST == 03:30 UTC


def test_once_and_end_date():
    s = _sched(recurrence="once", start_date=date(2026, 11, 10))
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert len(list(recurrence.occurrences(s, start, start + timedelta(days=30)))) == 1
    s2 = _sched(recurrence="daily", end_date=date(2026, 11, 4))
    assert len(list(recurrence.occurrences(s2, start, start + timedelta(days=30)))) == 3


def test_normalize_meetstream_word_shape_and_merge():
    payload = [
        {"participant": {"name": "Priya"}, "words": [{"text": "Hello", "start_timestamp": {"relative": 1.0}, "end_timestamp": {"relative": 1.5}}]},
        {"participant": {"name": "Priya"}, "words": [{"text": "again", "start_timestamp": {"relative": 2.0}, "end_timestamp": {"relative": 2.4}}]},
        {"speaker": "Sam", "transcript": "Hi there", "start_time": 3, "end_time": 4},
    ]
    turns = normalize_transcript(payload)
    assert [(t["speaker"], t["text"]) for t in turns] == [("Priya", "Hello again"), ("Sam", "Hi there")]


def test_silence_artifacts_dropped():
    """Live test: the transcriber turned silence into '.' and a 'Thank you.' every 30 s."""
    payload = [{"speaker": "T", "transcript": ".", "start_time": 0}]
    payload += [{"speaker": "T", "transcript": "Thank you.", "start_time": 30 * i} for i in range(1, 6)]
    payload.insert(2, {"speaker": "T", "transcript": "The export API is done but not tested.", "start_time": 45})
    turns = normalize_transcript(payload)
    assert [t["text"] for t in turns] == ["The export API is done but not tested."]


def test_normalize_wrapped_segments():
    assert normalize_transcript({"segments": [{"speakerName": "A", "transcript": "x"}]})[0]["speaker"] == "A"


def test_plain_transcript():
    turns = parse_plain_transcript("[00:05] Priya: I finished the API.\nSam: Working on UI\n  continued line")
    assert turns[0]["start"] == 5.0 and turns[1]["text"].endswith("continued line")


def test_match_employee():
    emps = [Employee(id="1", name="Priya Raman", aliases=["PR-laptop"]), Employee(id="2", name="Sam Okafor", email="sam.okafor@x.com"),
            Employee(id="3", name="Sam Lee")]
    assert identity.match_employee("Priya Raman (Guest)", emps).id == "1"
    assert identity.match_employee("pr-laptop", emps).id == "1"
    assert identity.match_employee("Priya", emps).id == "1"
    assert identity.match_employee("Sam", emps) is None  # ambiguous
    assert identity.match_employee("Sam O", emps).id == "2"
    assert identity.match_employee("sam okafor", emps).id == "2"


def test_status_mapping_and_stop_reason():
    assert map_remote_status("InWaitingRoom") == "waiting_room"
    assert map_remote_status("NotAllowed") == "not_admitted"
    assert stop_reason({"event": "bot.stopped", "bot_event": "bot.kicked", "bot_status": "Stopped"}) == "bot.kicked"
    assert stop_reason({"event": "bot.stopped", "bot_status": "Denied"}) == "bot.denied"


def test_chat_and_roster_normalisation():
    chats = normalize_chats({"chats": [{"sender": {"name": "Sam"}, "message": "opt out please"}, {"text": ""}]})
    assert chats == [{"author": "Sam", "text": "opt out please", "at": ""}]
    # Shape observed live on Google Meet: names live in "speakers", keyed by deviceId.
    meet = {"metadata": {}, "speakers": [{"deviceId": "d1", "name": "Thal"}, {"deviceId": "bot", "name": "Notetaker"}],
            "chatMessages": [{"deviceId": "bot", "text": "Recording notice"}, {"deviceId": "d1", "text": "opt out", "timestamp": "t"}]}
    assert normalize_chats(meet) == [{"author": "Notetaker", "text": "Recording notice", "at": ""},
                                     {"author": "Thal", "text": "opt out", "at": "t"}]
    assert roster_names([{"displayName": "A", "status": 1}, {"fullName": "B", "status": 2, "humanized_status": "Left"}]) == ["A"]


def test_provider_block_has_required_fields(monkeypatch):
    from app.config import settings
    from app.services.bots import _provider_block

    monkeypatch.setattr(settings, "TRANSCRIPT_PROVIDER", "meetstream")
    assert _provider_block() == {"meetstream": {"language": "en", "translate": False}}
    monkeypatch.setattr(settings, "TRANSCRIPT_PROVIDER", "assemblyai")
    assert _provider_block()["assemblyai"]["speech_models"] == ["universal-2"]


def test_paraphrased_titles_match_but_different_tasks_do_not():
    from app.models import WorkItem
    from app.services.tracker import _find_duplicate

    items = [WorkItem(title="Work on the improper response time"), WorkItem(title="Fix login bug")]
    assert _find_duplicate(items, "Address improper response time").title == "Work on the improper response time"
    assert _find_duplicate(items, "Fix signup bug") is None


def test_filler_only_segments_dropped_in_short_calls():
    """Live test 2: a 3-minute call left two 'Thank you.' lines - too few to count as repeats."""
    payload = [{"speaker": "T", "transcript": "I'm done with the export, testing response time today.", "start_time": 0},
               {"speaker": "T", "transcript": "Thank you Thank you", "start_time": 40},
               {"speaker": "T", "transcript": "Thank you.", "start_time": 70},
               {"speaker": "T", "transcript": "Thank you.", "start_time": 100}]
    assert [t["text"] for t in normalize_transcript(payload)] == ["I'm done with the export, testing response time today."]
