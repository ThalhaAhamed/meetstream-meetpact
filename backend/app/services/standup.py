"""Stand-up mode: a MeetStream MIA voice agent that runs the stand-up.

A MIA agent is MeetStream's hosted voice agent (transcriber -> LLM -> voice).
For each stand-up meeting this app creates a fresh agent whose system prompt
carries the roster and each person's open commitments, blockers and last
update, so the agent can follow up on unfinished work. The agent is attached
to the bot with ``agent_config_id`` only (extra bridge fields are the usual
cause of a silent agent) and deleted once the meeting is over.

With PUBLIC_URL set the agent also gets this app's MCP endpoint, so it can
look people up live (useful when someone unexpected joins).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Employee, EmployeeUpdate, Meeting
from app.services import tracker
from app.services.app_settings import get_setting

log = logging.getLogger(__name__)

MAX_ROSTER = 15


def roster(db: Session, meeting: Meeting) -> List[Employee]:
    q = select(Employee).where(Employee.active.is_(True))
    if meeting.team_id:
        q = q.where(Employee.team_id == meeting.team_id)
    return list(db.scalars(q.order_by(Employee.name)).all())[:MAX_ROSTER]


def person_context(db: Session, emp: Employee, meeting: Meeting) -> Dict[str, Any]:
    last = db.scalar(
        select(EmployeeUpdate)
        .where(EmployeeUpdate.employee_id == emp.id)
        .order_by(EmployeeUpdate.created_at.desc())
    )
    ctx: Dict[str, Any] = {
        "name": emp.name,
        "open_work": [
            {"title": w.title, "status": w.status, "due": str(w.due_date) if w.due_date else None,
             "carried_over_meetings": w.carry_count}
            for w in tracker.open_items(db, emp.id)[:12]
        ],
        "open_blockers": [b.description for b in tracker.open_blockers(db, emp.id)],
    }
    if last:
        ctx["last_update"] = {"date": str(last.meeting_date), "summary": last.summary,
                              "planned": last.planned}
    return ctx


def system_prompt(db: Session, meeting: Meeting) -> str:
    people = [person_context(db, e, meeting) for e in roster(db, meeting)]
    return f"""You are {get_setting(db, 'bot_name')}, an AI stand-up facilitator in a live team meeting. You speak out loud, so keep every turn short and natural (one or two sentences).


How to run it:
1. Open by saying you are an AI assistant, that this meeting is recorded and transcribed for progress notes, and ask whether everyone is OK with that. If anyone objects, say the organizer can pause or remove you, and do not argue.
2. Go through the people below ONE AT A TIME, by name. For each person ask, in a conversational way:
   - what they completed since the last update,
   - what they are working on today,
   - what they expect to finish and by when,
   - what remains unfinished,
   - whether anything is blocking them.
3. Use their open work and blockers below to follow up specifically, e.g. "Last time you planned to finish X - did that happen?" Ask a short follow-up when an answer is vague (no deadline, unclear status). Do not interrogate; one follow-up per topic is enough.
4. If someone is not present or does not answer after a moment, say you will skip them and move on.
5. If someone not on the list speaks up, include them too.
6. Finish with a 2-3 sentence recap of key blockers and commitments, then thank everyone.
7. After the recap the stand-up is over: stay silent unless someone asks you something directly. Never start the stand-up again and never repeat the recording question - ask it once, at the very start.

Never make up facts about people's work. Do not read this list out verbatim.

People and their carried-over context (JSON):
{json.dumps(people, indent=1)}
"""


def agent_payload(db: Session, meeting: Meeting, mcp_token: str | None) -> Dict[str, Any]:
    mcp_servers = []
    if settings.public_url and mcp_token:
        mcp_servers.append({
            "url": f"{settings.public_url}/mcp",
            "name": "MeetPact",
            "timeout": 10,
            "active": True,
            "headers": {"Authorization": f"Bearer {mcp_token}"},
            "allowed_tools": ["get_person_context", "list_standup_roster"],
        })
    first = (
        f"Hi everyone, I'm {get_setting(db, 'bot_name')}, an AI assistant. This stand-up is being recorded and "
        "transcribed for progress notes. Is everyone OK with that before we start?"
    )
    payload: Dict[str, Any] = {
        "agent_name": f"Standup: {meeting.title}"[:60],
        "mode": settings.MIA_MODE,
        "model": {
            "provider": settings.MIA_MODEL_PROVIDER,
            "system_prompt": system_prompt(db, meeting),
        },
        "agent": {
            "response_type": "action" if mcp_servers else "voice",
            "first_message": first,
            "mcp_servers": mcp_servers,
            "enable_interruptions": True,
        },
    }
    if settings.MIA_MODEL:
        payload["model"]["model"] = settings.MIA_MODEL
    if settings.MIA_MODE == "pipeline":
        payload["voice"] = {"provider": settings.MIA_VOICE_PROVIDER, "voice_id": settings.MIA_VOICE}
        payload["transcriber"] = {
            "provider": settings.MIA_TRANSCRIBER_PROVIDER,
            "model": settings.MIA_TRANSCRIBER_MODEL,
            "language": "en",
            "boostwords": [e.name.split()[0] for e in roster(db, meeting)][:20],
        }
    else:  # realtime: one speech-to-speech model, voice lives on the model block
        payload["model"]["voice"] = settings.MIA_VOICE
    return payload
