"""Sending bots into meetings and controlling them."""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Meeting
from app.services import consent, standup
from app.services.app_settings import get_setting, set_settings
from app.services.meetstream import MeetStreamError, meetstream

log = logging.getLogger(__name__)

PARTICIPANT_EVENTS = ["participant_events.join", "participant_events.leave"]


def _provider_block() -> Dict[str, Any]:
    """Post-call transcription config. The OpenAPI spec marks several sub-fields
    as required, so full configs are sent (see the MeetStream API reference)."""
    p = settings.TRANSCRIPT_PROVIDER.lower()
    lang = settings.TRANSCRIPT_LANGUAGE
    if p == "deepgram":
        return {"deepgram": {"model": "nova-3", "language": lang, "diarize": True, "punctuate": True,
                             "smart_format": True, "utterances": True}}
    if p == "assemblyai":
        return {"assemblyai": {
            "speech_models": ["universal-2"], "language_code": "en_us" if lang == "en" else lang,
            "speaker_labels": True, "punctuate": True, "format_text": True, "filter_profanity": False,
            "redact_pii": False, "keyterms_prompt": [], "auto_chapters": False, "entity_detection": False,
        }}
    return {"meetstream": {"language": lang, "translate": False}}


def mcp_token(db: Session) -> str:
    """Bearer token the stand-up agent uses to call /mcp. Created on first use."""
    tok = get_setting(db, "mcp_token")
    if not tok:
        tok = secrets.token_urlsafe(32)
        set_settings(db, {"mcp_token": tok})
    return tok


def build_payload(db: Session, meeting: Meeting, join_at: Optional[datetime]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "meeting_link": meeting.meeting_link,
        "bot_name": get_setting(db, "bot_name"),
        "video_required": False,  # the API defaults to True; audio is all we need
        "recording_config": {
            "transcript": {"provider": _provider_block()},
            "retention": {"type": "timed", "hours": settings.RETENTION_HOURS},
        },
        "automatic_leave": {
            "waiting_room_timeout": settings.WAITING_ROOM_TIMEOUT,
            "everyone_left_timeout": settings.EVERYONE_LEFT_TIMEOUT,
            "in_call_recording_timeout": max(600, settings.IN_CALL_RECORDING_TIMEOUT),
            "recording_permission_denied_timeout": 60,
        },
        # Custom attribute values must be strings.
        "custom_attributes": {"meeting_id": meeting.id, "app": "employee-progress-tracker"},
    }
    if join_at:
        payload["join_at"] = join_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if settings.public_url:
        payload["callback_url"] = f"{settings.public_url}/api/webhooks/meetstream"
        payload["recording_config"]["realtime_endpoints"] = [
            {"type": "webhook", "url": f"{settings.public_url}/api/webhooks/participants", "events": PARTICIPANT_EVENTS}
        ]
    return payload


async def launch(db: Session, meeting: Meeting, join_at: Optional[datetime] = None) -> Meeting:
    """Create the MeetStream bot for a meeting. Raises MeetStreamError."""
    if meeting.bot_id:
        return meeting
    payload = build_payload(db, meeting, join_at)
    if meeting.mode == "standup":
        agent = await meetstream.create_mia_agent(standup.agent_payload(db, meeting, mcp_token(db)))
        agent_id = agent.get("agent_config_id") or agent.get("id")
        if not agent_id:
            raise MeetStreamError("MeetStream did not return an agent_config_id for the stand-up agent.")
        meeting.mia_agent_id = str(agent_id)
        payload["agent_config_id"] = meeting.mia_agent_id
    try:
        resp = await meetstream.create_bot(payload, idempotency_key=str(uuid.UUID(hex=meeting.id)))
    except MeetStreamError:
        if meeting.mia_agent_id:
            await cleanup_agent(db, meeting)
        raise
    meeting.bot_id = str(resp.get("bot_id") or resp.get("id") or "") or None
    meeting.transcript_id = resp.get("transcript_id") or meeting.transcript_id
    meeting.bot_status = "scheduled" if join_at and join_at > datetime.now(timezone.utc) + timedelta(seconds=60) else "joining"
    db.commit()
    log.info("Bot %s created for meeting %s (%s)", meeting.bot_id, meeting.id, meeting.bot_status)
    return meeting


async def cleanup_agent(db: Session, meeting: Meeting) -> None:
    if not meeting.mia_agent_id:
        return
    try:
        await meetstream.delete_mia_agent(meeting.mia_agent_id)
    except MeetStreamError as exc:
        log.info("Could not delete MIA agent %s: %s", meeting.mia_agent_id, exc)
    meeting.mia_agent_id = None
    db.commit()


async def pause(db: Session, meeting: Meeting, actor: str) -> None:
    await meetstream.pause_recording(meeting.bot_id)
    meeting.recording_paused = True
    meeting.bot_status = "paused"
    consent.record(db, meeting, "paused", "Recording paused from the dashboard.", actor=actor)
    db.commit()
    try:
        await meetstream.send_message(meeting.bot_id, str(get_setting(db, "pause_ack")))
    except MeetStreamError:
        pass


async def resume(db: Session, meeting: Meeting, actor: str) -> None:
    await meetstream.resume_recording(meeting.bot_id)
    meeting.recording_paused = False
    meeting.bot_status = "recording"
    consent.record(db, meeting, "resumed", "Recording resumed from the dashboard.", actor=actor)
    db.commit()
    try:
        await meetstream.send_message(meeting.bot_id, str(get_setting(db, "resume_ack")))
    except MeetStreamError:
        pass


async def remove(db: Session, meeting: Meeting, actor: str) -> None:
    if meeting.bot_status == "scheduled":
        await meetstream.cancel_scheduled_bot(meeting.bot_id)
        meeting.bot_status = "cancelled"
        meeting.processing_status = "skipped"
        await cleanup_agent(db, meeting)
    else:
        await meetstream.remove_bot(meeting.bot_id)
        consent.record(db, meeting, "removed", "Bot removed from the meeting from the dashboard.", actor=actor)
    db.commit()
