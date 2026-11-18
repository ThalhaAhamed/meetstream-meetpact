import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["BACKGROUND_WORKERS"] = "false"
os.environ["MEETSTREAM_API_KEY"] = "test-key"
os.environ["PUBLIC_URL"] = ""
os.environ["SECRET_KEY"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Employee, Team, User  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def people(db):
    """A small org: admin, manager, a team lead and two employees."""
    team = Team(name="Platform")
    db.add(team)
    db.flush()
    emps = {}
    for key, name in [("lead", "Priya Raman"), ("sam", "Sam Okafor"), ("lena", "Lena Fischer"), ("mgr", "Maya Chen"), ("admin", "Alex Admin")]:
        e = Employee(name=name, email=f"{key}@t.local", team_id=team.id if key in ("lead", "sam", "lena") else None)
        db.add(e)
        emps[key] = e
    db.flush()
    team.lead_employee_id = emps["lead"].id
    users = {}
    for key, role in [("admin", "admin"), ("mgr", "manager"), ("lead", "employee"), ("sam", "employee"), ("lena", "employee")]:
        u = User(email=f"{key}@t.local", name=emps[key].name, role=role, password_hash=hash_password("password123"), employee_id=emps[key].id)
        db.add(u)
        users[key] = u
    db.commit()
    return {"team": team, "emps": emps, "users": users}


def login(client: TestClient, key: str):
    r = client.post("/api/auth/login", json={"email": f"{key}@t.local", "password": "password123"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c
