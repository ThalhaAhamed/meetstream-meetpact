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


def test_voice_presets_build_valid_mia_configs(client, db, people):
    from app.services import voices

    login(client, "admin")
    got = {}
    for name in ("gemini", "openai", "grok", "claude"):
        assert client.put("/api/setup/voices", json={"provider": name}).status_code == 200
        got[name] = voices.model_block(db, "Prompt")
    assert got["gemini"] == {"mode": "realtime", "model": {"provider": "google", "system_prompt": "Prompt", "voice": "Puck"}}
    assert got["openai"]["model"] == {"provider": "openai", "system_prompt": "Prompt", "model": "gpt-realtime-mini", "voice": "coral"}
    assert "model" not in {k for k in got["grok"]["model"] if k == "model"} and got["grok"]["model"]["voice"] == "Ara"
    assert got["claude"]["mode"] == "pipeline" and got["claude"]["model"]["model"] == "claude-haiku-4-5"
    assert got["claude"]["voice"]["provider"] == "elevenlabs" and got["claude"]["transcriber"]["provider"] == "deepgram"
    assert client.put("/api/setup/voices", json={"provider": "grok", "voice": "Nope"}).status_code == 400
    assert client.put("/api/setup/voices", json={"provider": "grok", "voice": "Rex"}).json()["current"] == {"name": "grok", "voice": "Rex"}
