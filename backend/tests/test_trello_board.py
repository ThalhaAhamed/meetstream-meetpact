"""Team boards on Trello: import, ownership, status, writes back, the host's brief."""
import asyncio
from datetime import date, timedelta

import pytest

from app.models import Meeting, Team, WorkItem
from app.services import trello_board as tb
from tests.conftest import login


class FakeTrello:
    def __init__(self):
        self.lists = [{"id": "L1", "name": "To Do"}, {"id": "L2", "name": "Doing"}, {"id": "L3", "name": "Done"},
                      {"id": "L4", "name": "Descoped"}]
        past = (date.today() - timedelta(days=2)).isoformat() + "T12:00:00.000Z"
        self.cards = [
            {"id": "c1", "name": "Ship invoice export", "idList": "L2", "idMembers": ["m1"], "due": past,
             "dueComplete": False, "shortUrl": "https://trello.com/c/1", "pos": 1},
            {"id": "c2", "name": "Write docs", "idList": "L1", "idMembers": [], "due": None, "dueComplete": False,
             "shortUrl": "https://trello.com/c/2", "pos": 2},
            {"id": "c3", "name": "Old idea", "idList": "L4", "idMembers": [], "due": None, "dueComplete": False,
             "shortUrl": "https://trello.com/c/3", "pos": 3},
        ]
        self.members = [{"id": "m1", "fullName": "Priya Raman", "username": "priya"},
                        {"id": "m2", "fullName": "Someone Else", "username": "else"}]
        self.calls = []

    async def __call__(self, db, method, path, **params):
        self.calls.append((method, path, params))
        if path.endswith("/lists"):
            return self.lists
        if path.endswith("/cards") and method == "GET":
            return self.cards
        if path.endswith("/members"):
            return self.members
        if path.startswith("/boards/"):
            return {"name": "Team board", "url": "https://trello.com/b/x"}
        if path == "/cards" and method == "POST":
            card = {"id": f"new{len(self.cards)}", "name": params["name"], "idList": params["idList"],
                    "idMembers": [params["idMembers"]] if params.get("idMembers") else [], "due": None,
                    "dueComplete": False, "shortUrl": "https://trello.com/c/new", "pos": 9}
            self.cards.append(card)
            return card
        if path.startswith("/cards/") and method == "PUT":
            cid = path.split("/")[2]
            next(c for c in self.cards if c["id"] == cid)["idList"] = params["idList"]
            return {}
        if path == "/members/me":
            return {"fullName": "Thalha"}
        raise AssertionError(path)


@pytest.fixture
def trello(monkeypatch, db, people):
    fake = FakeTrello()
    monkeypatch.setattr(tb, "_call", fake)
    team = db.query(Team).first()
    asyncio.run(tb.connect_team(db, team, "B1"))
    return fake, team


def test_guess_status_from_list_names():
    assert [tb.guess_status(n) for n in ("To Do", "Doing", "In review", "Blocked", "DONE", "Descoped/Postponed", "Ideas")] == \
        ["planned", "in_progress", "in_progress", "blocked", "completed", "ignore", "planned"]


def test_sync_imports_cards_owners_and_statuses(db, trello):
    fake, team = trello
    stats = asyncio.run(tb.sync_team(db, team))
    assert stats["created"] == 2  # the Descoped list is ignored
    items = {w.external_id: w for w in db.query(WorkItem).filter(WorkItem.external_board_id == "B1")}
    priya = people_by_name(db, "Priya Raman")
    assert items["c1"].status == "in_progress" and items["c1"].employee_id == priya.id
    assert priya.trello_member_id == "m1"  # matched by name once, then remembered
    assert items["c2"].employee_id is None and items["c1"].external_members[0]["name"] == "Priya Raman"
    # Card finished in Trello, another archived -> statuses follow.
    fake.cards[0]["idList"] = "L3"
    fake.cards.pop(1)
    asyncio.run(tb.sync_team(db, team))
    db.expire_all()
    assert db.get(WorkItem, items["c1"].id).status == "completed"
    assert db.get(WorkItem, items["c2"].id).status == "dropped"


def test_meeting_changes_create_and_move_cards(db, trello):
    fake, team = trello
    asyncio.run(tb.sync_team(db, team))
    priya = people_by_name(db, "Priya Raman")
    m = Meeting(title="Stand-up", team_id=team.id)
    db.add(m)
    db.flush()
    done = db.query(WorkItem).filter_by(external_id="c1").one()
    done.status, done.last_meeting_id = "completed", m.id
    new = WorkItem(title="Pair on sync", employee_id=priya.id, status="planned", created_meeting_id=m.id)
    db.add(new)
    db.commit()
    stats = asyncio.run(tb.push_meeting_changes(db, m))
    assert stats == {"cards": 1, "moved": 1}
    assert next(c for c in fake.cards if c["id"] == "c1")["idList"] == "L3"
    post = next(c for c in fake.calls if c[0] == "POST")
    assert post[2]["idList"] == "L1" and post[2]["idMembers"] == "m1"


def test_board_brief_for_the_standup_host(db, trello):
    _, team = trello
    asyncio.run(tb.sync_team(db, team))
    brief = tb.board_brief(db, team)
    assert '"Team board" (2 open)' in brief
    assert "Priya Raman: \"Ship invoice export\" (In progress, due" in brief and "(overdue)" in brief
    assert "Unassigned: \"Write docs\" (To do)" in brief


def test_board_api_and_move(client, db, trello):
    fake, team = trello
    login(client, "sam")  # Sam is on the team
    b = client.get(f"/api/teams/{team.id}/board").json()
    assert b["source"] == "trello" and [l["name"] for l in b["lists"]] == ["To Do", "Doing", "Done", "Descoped"]
    doing = b["lists"][1]["cards"][0]
    assert doing["title"] == "Ship invoice export" and doing["overdue"] and doing["members"][0]["initials"] == "PR"
    assert client.post(f"/api/teams/{team.id}/board/move", json={"card_id": "c1", "list_id": "L3"}).json() == {"ok": True}
    assert db.query(WorkItem).filter_by(external_id="c1").one().status == "completed"
    login(client, "sam")
    assert client.put(f"/api/teams/{team.id}/board", json={"source": "native"}).status_code == 403


def people_by_name(db, name):
    from app.models import Employee
    return db.query(Employee).filter_by(name=name).one()


def test_card_pushed_before_is_not_imported_twice(db, trello):
    fake, team = trello
    old = WorkItem(title="Write docs", status="planned", external_provider="trello", external_id="c2")
    db.add(old)
    db.commit()
    asyncio.run(tb.sync_team(db, team))
    assert db.query(WorkItem).filter_by(external_id="c2").count() == 1
    assert db.query(WorkItem).filter_by(external_id="c2").one().external_board_id == "B1"


def test_older_work_is_not_pushed_as_new_cards(db, trello):
    fake, team = trello
    asyncio.run(tb.sync_team(db, team))
    priya = people_by_name(db, "Priya Raman")
    old_meeting, m = Meeting(title="Last week", team_id=team.id), Meeting(title="Today", team_id=team.id)
    db.add_all([old_meeting, m])
    db.flush()
    old = WorkItem(title="Old task from last week", employee_id=priya.id, status="in_progress",
                   created_meeting_id=old_meeting.id, last_meeting_id=m.id)  # carried over today
    db.add(old)
    db.commit()
    assert asyncio.run(tb.push_meeting_changes(db, m))["cards"] == 0
    assert not any(c[0] == "POST" for c in fake.calls)
