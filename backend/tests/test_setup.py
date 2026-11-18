"""Setup wizard: keys saved in the app, .env wins, secrets never sent back."""
from app.config import settings
from app.services import saved_keys
from tests.conftest import login


def test_keys_saved_in_app_apply_and_stay_secret(client, db, people, monkeypatch):
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", None)
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    monkeypatch.setattr(saved_keys, "_from_env", {"SLACK_WEBHOOK_URL": False, "SMTP_HOST": False, "MEETSTREAM_API_KEY": True})
    monkeypatch.setattr(saved_keys, "_applied", {})
    login(client, "admin")
    r = client.put("/api/setup/keys", json={"SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/x", "SMTP_HOST": "smtp.gmail.com",
                                            "MEETSTREAM_API_KEY": "should-not-replace-env"})
    assert r.status_code == 200
    keys = r.json()
    assert settings.SLACK_WEBHOOK_URL == "https://hooks.slack.com/services/x"
    assert keys["SLACK_WEBHOOK_URL"] == {"set": True, "from_env": False, "value": None}  # secret: not returned
    assert keys["SMTP_HOST"]["value"] == "smtp.gmail.com"
    assert keys["MEETSTREAM_API_KEY"]["from_env"] is True and settings.MEETSTREAM_API_KEY != "should-not-replace-env"
    # Clearing removes it again.
    client.put("/api/setup/keys", json={"SLACK_WEBHOOK_URL": ""})
    assert not settings.SLACK_WEBHOOK_URL
    assert client.get("/api/setup").json()["slack"] is False
    assert client.put("/api/setup/keys", json={"NOPE": "x"}).status_code == 400
    login(client, "mgr")
    assert client.get("/api/setup").status_code == 403


def test_finish_marks_onboarding_done(client, db, people):
    login(client, "admin")
    assert client.get("/api/setup").json()["done"] is False
    client.post("/api/setup/done")
    assert client.get("/api/setup").json()["done"] is True
