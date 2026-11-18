"""Which voice runs the AI stand-up host (MeetStream MIA).

Four presets, from MeetStream's MIA docs (create-agent-config):

* Gemini Live - realtime, provider "google". Works on a MeetStream account
  without adding a key.
* OpenAI      - realtime, provider "openai" (gpt-realtime-mini).
* Grok        - realtime, provider "xai" (MeetStream picks the model).
* Claude      - pipeline: Deepgram transcriber -> Claude -> ElevenLabs voice
  (Anthropic has no realtime model).

MeetStream uses the provider keys saved in its dashboard (Configure ->
Integrations); MeetPact cannot add them. `check()` asks MeetStream whether a
preset is usable by creating a throwaway agent config and deleting it.

The choice is an admin setting ("standup_voice_provider", "standup_voice");
without one, the MIA_* variables in .env decide, as before.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.services.app_settings import get_setting
from app.services.meetstream import MeetStreamError, meetstream

INTEGRATIONS_URL = "https://app.meetstream.ai"

PRESETS: Dict[str, Dict[str, Any]] = {
    "gemini": {
        "label": "Gemini Live", "mode": "realtime", "provider": "google", "model": None,
        "voices": [{"id": v, "label": v} for v in ("Puck", "Charon", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr")],
        "default_voice": "Puck", "needs": None,
        "note": "Speech-to-speech. Works without adding a key to MeetStream.",
    },
    "openai": {
        "label": "OpenAI", "mode": "realtime", "provider": "openai", "model": "gpt-realtime-mini",
        "voices": [{"id": v, "label": v.capitalize()} for v in
                   ("coral", "alloy", "ash", "ballad", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse")],
        "default_voice": "coral", "needs": "OpenAI",
        "note": "Speech-to-speech. Needs your OpenAI key in MeetStream (Configure → Integrations → Models).",
    },
    "grok": {
        "label": "Grok", "mode": "realtime", "provider": "xai", "model": None,
        "voices": [{"id": v, "label": v} for v in ("Ara", "Eve", "Leo", "Rex", "Sal")],
        "default_voice": "Ara", "needs": "xAI",
        "note": "Speech-to-speech. Needs your xAI key in MeetStream (Configure → Integrations → Models).",
    },
    "claude": {
        "label": "Claude", "mode": "pipeline", "provider": "anthropic", "model": "claude-haiku-4-5",
        "voice_provider": "elevenlabs",
        "voices": [{"id": "21m00Tcm4TlvDq8ikWAM", "label": "Rachel"}, {"id": "EXAVITQu4vr4xnSDxMaL", "label": "Sarah"},
                   {"id": "pNInz6obpgDQGcFmaJgB", "label": "Adam"}, {"id": "ErXwobaYiN019PkySvjV", "label": "Antoni"},
                   {"id": "cjVigY5qzO86Huf0OWal", "label": "Eric"}],
        "default_voice": "21m00Tcm4TlvDq8ikWAM", "needs": None,
        "note": "Listens with Deepgram, thinks with Claude, speaks with ElevenLabs. A little slower to answer than speech-to-speech.",
    },
}

_FROM_ENV = {"google": "gemini", "openai": "openai", "xai": "grok", "anthropic": "claude"}


def current(db: Session) -> Dict[str, Any]:
    """The chosen preset and voice (admin setting, else .env's MIA_*)."""
    name = get_setting(db, "standup_voice_provider") or _FROM_ENV.get(settings.MIA_MODEL_PROVIDER, "gemini")
    preset = PRESETS.get(name) or PRESETS["gemini"]
    name = next(k for k, v in PRESETS.items() if v is preset)
    voice = get_setting(db, "standup_voice")
    if not voice and not get_setting(db, "standup_voice_provider"):
        voice = settings.MIA_VOICE  # .env choice
    if voice not in {v["id"] for v in preset["voices"]} and not (voice and name == "claude"):
        voice = preset["default_voice"]
    return {"name": name, "voice": voice, **preset}


def model_block(db: Session, system_prompt: str) -> Dict[str, Any]:
    """The parts of a MIA config that depend on the voice choice."""
    c = current(db)
    use_env = not get_setting(db, "standup_voice_provider")
    out: Dict[str, Any] = {"mode": c["mode"], "model": {"provider": c["provider"], "system_prompt": system_prompt}}
    model = (settings.MIA_MODEL if use_env and settings.MIA_MODEL else None) or c["model"]
    if model:
        out["model"]["model"] = model
    if c["mode"] == "realtime":
        out["model"]["voice"] = c["voice"]
    else:
        out["voice"] = {"provider": c.get("voice_provider", settings.MIA_VOICE_PROVIDER), "voice_id": c["voice"]}
        out["transcriber"] = {"provider": settings.MIA_TRANSCRIBER_PROVIDER, "model": settings.MIA_TRANSCRIBER_MODEL,
                              "language": "en"}
    return out


def describe(db: Session) -> Dict[str, Any]:
    c = current(db)
    return {
        "current": {"name": c["name"], "voice": c["voice"]},
        "presets": [{"name": k, "label": v["label"], "mode": v["mode"], "voices": v["voices"], "needs": v["needs"],
                     "note": v["note"], "default_voice": v["default_voice"]} for k, v in PRESETS.items()],
        "integrations_url": INTEGRATIONS_URL,
    }


async def check(db: Session) -> str:
    """Ask MeetStream whether the chosen voice can be used. Raises ValueError."""
    if not meetstream.configured:
        raise ValueError("Add the MeetStream API key first.")
    c = current(db)
    body = {"agent_name": "MeetPact voice check", "agent": {"response_type": "voice", "first_message": "Hi"},
            **model_block(db, "Voice check.")}
    try:
        created = await meetstream.create_mia_agent(body)
    except MeetStreamError as exc:
        text = str(exc)
        if "API key not configured" in text:
            raise ValueError(f"MeetStream doesn't have a key for {c['label']} yet. Add it at app.meetstream.ai under "
                             f"Configure → Integrations, then check again.")
        raise ValueError(text)
    agent_id = created.get("agent_config_id") or created.get("id")
    if agent_id:
        try:
            await meetstream.delete_mia_agent(str(agent_id))
        except MeetStreamError:
            pass
    return f"MeetStream accepts {c['label']} with the voice {_voice_label(c)}."


def _voice_label(c: Dict[str, Any]) -> str:
    return next((v["label"] for v in c["voices"] if v["id"] == c["voice"]), c["voice"])
