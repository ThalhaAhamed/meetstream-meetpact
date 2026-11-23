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


def intro_text(db: Session) -> str:
    """The host's first words after joining (Admin -> Bot and reports)."""
    text = str(get_setting(db, "standup_intro") or "").strip()
    try:
        text = text.format(bot_name=get_setting(db, "bot_name"))
    except (KeyError, IndexError, ValueError):
        pass  # braces typed by an admin are left as they are
    return text or f"Hi everyone, I'm {get_setting(db, 'bot_name')}. Let's get started."


def early_first_message(db: Session) -> str:
    """First words when the host arrives before the start time, to a room
    that may still be empty: the real introduction comes once people speak."""
    return f"Hi, I'm {get_setting(db, 'bot_name')}. I'll start the stand-up once people are here, just say hello when you're ready."


def system_prompt(db: Session, meeting: Meeting, can_leave: bool, live_roster: bool = False,
                  early: bool = False, signed_in: bool = False) -> str:
    """``signed_in``: the bot joins without knocking, so when it is also early it
    is in the call before everyone and sees each person arrive."""
    people = [person_context(db, e, meeting) for e in roster(db, meeting)]
    names = ", ".join(p["name"] for p in people) or "whoever is present"
    leave = (
        "Then call the end_meeting tool so you leave the call."
        if can_leave else
        "Then stay completely silent: you will leave the call automatically once everyone has left."
    )
    if live_roster and early and signed_in:
        who = (
            "You joined before anyone else, so the list_participants_now tool shows everyone in the call. Only "
            "ask expected people it lists as present; do not call on anyone who has not joined. Call it "
            "again before each new person and before the open floor, so you include people who arrive late. Ask "
            "anyone present who is not on your list for their update too (use get_person_context for their history). "
            "Leave people it says may have left until last and ask them once; if they answer, they are back. "
            "Never say aloud that someone has left. Never talk about your tools, lists or what you can or cannot see; just run the meeting."
        )
        order = ("call list_participants_now, then in a few words say the order, using only the expected people "
                 "who are present")
    elif live_roster:
        who = (
            "Call the list_participants_now tool at the start of the round, before each new person and before the "
            "open floor. It tells you who joined or left since you arrived (people already there when you joined "
            "are not in it). Ask the people it says joined first, in the order they joined, then go through the "
            "rest of the expected people by name; if someone does not answer after a moment, say you will skip them. "
            "Leave people it says may have left until last and ask them once; if they answer, they are back. "
            "Ask anyone who joined and is not on your list for their "
            "update too (use get_person_context for their history). Never say aloud that someone has left, and "
            "never talk about your tools, lists or what you can or cannot see; just run the meeting."
        )
        order = "call list_participants_now, then in a few words say the order: people who joined first, then the rest"
    else:
        who = ("You cannot see who is in the call. If someone does not answer after a moment, say you will skip them. "
               "If someone not on the list speaks up, include them.")
        order = f"in a few words say the order ({names})"
    no_consent = "Please do not ask about recording or consent: the organizer has told people the meeting is recorded."
    if early:
        opening = (f"You arrived a couple of minutes before the start and your first message told people to say "
                   f"hello when they are ready. Stay silent until someone speaks to you. If they ask you to wait for "
                   f"others, wait until someone tells you to start. Then say: \"{intro_text(db)}\" and {order}, "
                   f"then start with the first person straight away. {no_consent}")
    else:
        opening = ("Your first message already introduced you and told people you will ask each of them what they "
                   "worked on, their updates and their status. Do not repeat that introduction. "
                   f"{no_consent} {order[0].upper() + order[1:]}, then start with the first person straight away.")
    return f"""You are {get_setting(db, 'bot_name')}, an AI stand-up facilitator running a live team meeting from start to finish. You speak out loud, so keep every turn short and natural (one or two sentences). You lead and keep a brisk pace: people should never have to tell you what comes next or ask whether you are still there.

Run the meeting in these phases, in order, exactly once each:

1. OPENING. {opening}

2. ROUND. Go through the people ONE AT A TIME, by name. For each person ask, conversationally:
   - what they completed since the last update,
   - what they are working on today,
   - what they expect to finish and by when,
   - whether anything is blocking them.
   You can ask two of these together. Use their carried-over context below to follow up specifically, e.g. "Last time you said X was nearly done - did it land?" Ask at most ONE follow-up per person, only when the status or deadline is unclear; accept whatever they answer (even "not sure yet") and never ask the same thing twice. Briefly acknowledge, then hand over to the next person by name. {who}

3. OPEN FLOOR. First ask once: "Is there anyone else here who'd like to give an update?" (you can't see everyone who was already in the call, so this catches people not on your list) and take each update the same way, briefly. Then ask once: "Is there anything else anyone wants to raise before we wrap up?" Handle anything raised briefly.

4. CLOSE. Give a 2-3 sentence recap: who committed to what (with deadlines) and any blockers. Then say: "That's everything for today. Thanks everyone - I'll leave the meeting now." {leave}

Rules: never restart the meeting or repeat a phase. After the closing line, do not speak again. Never make up facts about people's work, and do not read the context below out verbatim.

People and their carried-over context (JSON):
{json.dumps(people, indent=1)}
{board_section(db, meeting)}"""


def board_section(db: Session, meeting: Meeting) -> str:
    """The team's Trello board, if it uses one: open cards and who owns them."""
    from app.models import Team
    from app.services import trello_board

    brief = trello_board.board_brief(db, db.get(Team, meeting.team_id) if meeting.team_id else None)
    if not brief:
        return ""
    return f"""
TEAM BOARD. This is what is still open on the team's task board. In the ROUND, ask each person about their own
open cards by name (especially overdue ones). In OPEN FLOOR, mention any overdue or unassigned cards in one
sentence and ask who will take them. Do not read the list out.
{brief}
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


def agent_payload(db: Session, meeting: Meeting, mcp_token: str | None, early: bool = False,
                  signed_in: bool = False) -> Dict[str, Any]:
    """``early``: the bot is booked to join before the meeting starts.
    ``signed_in``: it joins signed in to Google, without knocking."""
    mcp_servers, functions = [], []
    if settings.public_url and mcp_token:
        mcp_servers.append({
            "url": f"{settings.public_url}/mcp",
            "timeout": 10,
            "headers": {"Authorization": f"Bearer {mcp_token}"},
            "allowed_tools": ["get_person_context", "list_standup_roster"],
        })
        functions.append(participants_function(mcp_token))
        functions.append(leave_function(mcp_token))
    first = early_first_message(db) if early else intro_text(db)
    from app.services import voices

    prompt = system_prompt(db, meeting, can_leave=bool(functions), live_roster=bool(mcp_servers), early=early,
                           signed_in=signed_in)
    payload: Dict[str, Any] = {
        "agent_name": f"Standup: {meeting.title}"[:60],
        **voices.model_block(db, prompt),
        "agent": {
            # "action" lets the agent call tools (MCP servers and custom functions).
            "response_modality": "action" if (mcp_servers or functions) else "audio",
            "mcp_servers": mcp_servers,
            "custom_functions": functions,
            "enable_interruptions": True,
        },
    }
    payload["model"]["first_message"] = first  # spoken first; belongs to the model block
    if "transcriber" in payload:  # pipeline: help the transcriber with the team's names
        payload["transcriber"]["boostwords"] = [e.name.split()[0] for e in roster(db, meeting)][:20]
    return payload
