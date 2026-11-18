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


def system_prompt(db: Session, meeting: Meeting, can_leave: bool, live_roster: bool = False) -> str:
    people = [person_context(db, e, meeting) for e in roster(db, meeting)]
    names = ", ".join(p["name"] for p in people) or "whoever is present"
    leave = (
        "Then call the end_meeting tool so you leave the call."
        if can_leave else
        "Then stay completely silent: you will leave the call automatically once everyone has left."
    )
    who = (
        "Call the list_participants_now tool at the start of the round and again before the open floor. "
        "It tells you who joined or left since you arrived (people already there when you joined are not in it). "
        "Skip expected people it says have left, and ask anyone who joined and is not on your list for their "
        "update too (use get_person_context for their history). Never talk about your tools, lists or "
        "what you can or cannot see; just run the meeting."
        if live_roster else
        "You cannot see who is in the call. If someone does not answer after a moment, say you will skip them. "
        "If someone not on the list speaks up, include them."
    )
    consent = (
        "Your first message greeted everyone and asked whether recording is OK. Wait for the answer; if someone "
        "objects, say the organizer can pause or remove you, and do not argue. Ask this only once."
        if get_setting(db, "standup_ask_consent") else
        "Your first message greeted everyone. The organizer has already told people the meeting is recorded, so "
        "do not ask about recording or consent."
    )
    return f"""You are {get_setting(db, 'bot_name')}, an AI stand-up facilitator running a live team meeting from start to finish. You speak out loud, so keep every turn short and natural (one or two sentences). You lead and keep a brisk pace: people should never have to tell you what comes next or ask whether you are still there.

Run the meeting in these phases, in order, exactly once each:

1. OPENING. {consent} In one sentence say how this will go: you will go round each person ({names}), then ask if there's anything else, then wrap up. Then start with the first person straight away.

2. ROUND. Go through the people ONE AT A TIME, by name. For each person ask, conversationally:
   - what they completed since the last update,
   - what they are working on today,
   - what they expect to finish and by when,
   - whether anything is blocking them.
   You can ask two of these together. Use their carried-over context below to follow up specifically, e.g. "Last time you said X was nearly done - did it land?" Ask at most ONE follow-up per person, only when the status or deadline is unclear; accept whatever they answer (even "not sure yet") and never ask the same thing twice. Briefly acknowledge, then hand over to the next person by name. {who}

3. OPEN FLOOR. Ask once: "Is there anything else anyone wants to raise before we wrap up?" Handle anything raised briefly.

4. CLOSE. Give a 2-3 sentence recap: who committed to what (with deadlines) and any blockers. Then say: "That's everything for today. Thanks everyone - I'll leave the meeting now." {leave}

Rules: never restart the meeting or repeat a phase. After the closing line, do not speak again. Never make up facts about people's work, and do not read the context below out verbatim.

People and their carried-over context (JSON):
{json.dumps(people, indent=1)}
"""


def participants_function(mcp_token: str) -> Dict[str, Any]:
    """Custom function: who is in the call right now, from MeetStream's live
    participant_events webhooks (only delivered when PUBLIC_URL is set)."""
    return {
        "name": "list_participants_now",
        "description": "List the people currently in the meeting (bots excluded). Call it before the round "
                       "and before the open floor.",
        "url": f"{settings.public_url}/api/agent/participants",
        "method": "POST",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "headers": {"Authorization": f"Bearer {mcp_token}"},
    }


def leave_function(mcp_token: str) -> Dict[str, Any]:
    """Custom function the agent calls after its goodbye. MeetStream POSTs
    {"name", "bot": {"bot_id"}, "args"} to it (same shape the MeetStream
    companion app relies on)."""
    return {
        "name": "end_meeting",
        "description": "Leave the meeting. Call this only after you have given the closing recap and said goodbye, "
                       "when nobody has anything else to raise.",
        "url": f"{settings.public_url}/api/agent/leave",
        "method": "POST",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string", "description": "One short sentence, e.g. 'stand-up finished'."}}, "required": []},
        "headers": {"Authorization": f"Bearer {mcp_token}"},
    }


def agent_payload(db: Session, meeting: Meeting, mcp_token: str | None) -> Dict[str, Any]:
    mcp_servers, functions = [], []
    if settings.public_url and mcp_token:
        mcp_servers.append({
            "url": f"{settings.public_url}/mcp",
            "name": "MeetPact",
            "timeout": 10,
            "active": True,
            "headers": {"Authorization": f"Bearer {mcp_token}"},
            "allowed_tools": ["get_person_context", "list_standup_roster"],
        })
        functions.append(participants_function(mcp_token))
        functions.append(leave_function(mcp_token))
    first = (
        f"Hi everyone, I'm {get_setting(db, 'bot_name')}, the AI facilitator for today's stand-up. "
        + ("This meeting is recorded and transcribed for progress notes. Is everyone OK with that before we start?"
           if get_setting(db, "standup_ask_consent") else "Let's get started.")
    )
    payload: Dict[str, Any] = {
        "agent_name": f"Standup: {meeting.title}"[:60],
        "mode": settings.MIA_MODE,
        "model": {
            "provider": settings.MIA_MODEL_PROVIDER,
            "system_prompt": system_prompt(db, meeting, can_leave=bool(functions), live_roster=bool(mcp_servers)),
        },
        "agent": {
            # "action" lets the agent call tools (MCP servers and custom functions).
            "response_type": "action" if (mcp_servers or functions) else "voice",
            "first_message": first,
            "mcp_servers": mcp_servers,
            "custom_functions": functions,
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
