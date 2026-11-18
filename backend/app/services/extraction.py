"""Meeting analysis with Claude.

One structured-output call per meeting. The model is given the transcript
*and* each attendee's open work items and blockers from earlier meetings, so
it can say "item X is now done" or "still blocked" by id - that is what makes
progress continuous across meetings instead of a pile of disconnected notes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date
from typing import List, Literal, Optional

import anthropic
import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import settings

log = logging.getLogger(__name__)

Status = Literal["planned", "in_progress", "blocked", "completed", "dropped"]


class Commitment(BaseModel):
    text: str
    due_date: Optional[str] = Field(description="YYYY-MM-DD if a deadline was stated or clearly implied, else null")


class ExistingItemUpdate(BaseModel):
    work_item_id: str = Field(description="id of an item from the person's open work items list")
    new_status: Status | Literal["unchanged"]
    note: str = Field(description="one short sentence of evidence from the meeting")
    due_date: Optional[str] = Field(description="new YYYY-MM-DD deadline if one was given, else null")


class NewWorkItem(BaseModel):
    title: str = Field(description="short imperative task title, e.g. 'Ship invoice export API'")
    status: Status
    due_date: Optional[str]
    project: Optional[str] = Field(description="project name from the project list if it clearly applies, else null")


class EmployeeReport(BaseModel):
    employee_id: Optional[str] = Field(description="id from the roster, or null if the speaker is not on the roster")
    speaker_name: str
    summary: str = Field(description="2-3 sentence summary of this person's update")
    completed: List[str]
    in_progress: List[str]
    planned: List[str] = Field(description="what they plan to do next / today")
    pending: List[str] = Field(description="previously planned work that is still not finished")
    blockers: List[str]
    commitments: List[Commitment] = Field(description="explicit promises, with deadlines where stated")
    existing_item_updates: List[ExistingItemUpdate]
    new_work_items: List[NewWorkItem] = Field(description="work not already in their open items list")
    resolved_blocker_ids: List[str] = Field(description="ids from their open blockers that are now resolved")


class ActionItem(BaseModel):
    title: str
    owner_name: Optional[str]
    owner_employee_id: Optional[str]
    due_date: Optional[str]


class MeetingAnalysis(BaseModel):
    overview: str = Field(description="one paragraph summary of the meeting")
    key_points: List[str]
    decisions: List[str]
    action_items: List[ActionItem]
    open_questions: List[str]
    employee_reports: List[EmployeeReport] = Field(description="one per person who gave any work update")


SYSTEM_PROMPT = """You analyse workplace meetings for a team progress tracker.

You receive a meeting transcript plus, for each known attendee, their open work items and open blockers carried over from earlier meetings. Produce meeting notes and a per-person progress update.

Rules:
- Only record what was actually said. Never invent tasks, deadlines or progress. Leave lists empty when nothing applies.
- Attribute work to the person it belongs to, even if someone else said it ("Priya finished the export yesterday" is Priya's completion).
- For an open work item that was discussed, add an existing_item_updates entry with its id and the new status (or "unchanged" if it was mentioned without a status change). Do not create a new_work_items entry for something that is already on the open list.
- "pending" means work the person previously planned that is still unfinished.
- Resolve relative dates ("by Friday", "tomorrow") against the meeting date. Use YYYY-MM-DD.
- Use roster ids exactly as given. If a speaker is not on the roster, set employee_id to null.
- Keep titles short and specific. Write in plain English.
- Refer to people by name. When a pronoun is needed, use "they"; never infer gender from a name.
- "blockers" lists only NEW blockers. A blocker already in the person's open_blockers stays open by itself; do not restate it in other words. Put its id in resolved_blocker_ids only if it was said to be resolved.
- A deadline for an existing open item goes in that item's existing_item_updates.due_date; do not also add it as a separate commitment.
- In an AI-led stand-up (mode "standup") the AI facilitator asks the questions. Transcription can attach a sentence to the wrong speaker, so treat questions, greetings, recaps and recording notices as the facilitator's even if labelled with a person's name, and record only what the people themselves reported.
- Never invent placeholder titles such as "Unnamed task". If someone does not name the work, title it from what they said about it (e.g. "Finish and test current feature"), or leave it out."""


def _client() -> anthropic.AsyncAnthropic:
    # ANTHROPIC_API_KEY from settings when set; otherwise the SDK resolves
    # credentials from the environment (ANTHROPIC_API_KEY, `ant auth login`).
    if settings.ANTHROPIC_API_KEY:
        return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return anthropic.AsyncAnthropic()


class AnalysisError(Exception):
    pass


def build_prompt(
    *,
    title: str,
    meeting_date: Optional[date],
    slot: str,
    mode: str,
    roster: List[dict],
    projects: List[str],
    transcript: str,
) -> str:
    context = {
        "meeting": {"title": title, "date": meeting_date.isoformat() if meeting_date else None, "slot": slot, "mode": mode},
        "projects": projects,
        "roster": roster,
    }
    return (
        "<context>\n" + json.dumps(context, indent=1, default=str) + "\n</context>\n\n"
        "<transcript>\n" + transcript + "\n</transcript>\n\n"
        "Analyse this meeting."
    )


def provider() -> str:
    """Which model provider analyses transcripts: ANALYSIS_PROVIDER, else
    whichever key is configured (Claude preferred when both are)."""
    choice = (settings.ANALYSIS_PROVIDER or "").lower().strip()
    if choice in ("anthropic", "claude"):
        return "anthropic"
    if choice == "gemini":
        return "gemini"
    if settings.GEMINI_API_KEY and not settings.ANTHROPIC_API_KEY:
        return "gemini"
    return "anthropic"


async def analyse_meeting(prompt: str) -> MeetingAnalysis:
    if provider() == "gemini":
        analysis = await _analyse_with_gemini(prompt)
    else:
        analysis = await _analyse_with_claude(prompt)
    return await neutralise_pronouns(analysis)


# Models sometimes guess a gender from a name despite the prompt (seen live
# with Gemini: "He is currently engaged..."). Any text that still uses a
# gendered pronoun is rewritten in one small follow-up call.
_GENDERED = re.compile(r"\b(he|she|him|his|her|hers|himself|herself)\b", re.IGNORECASE)
PRONOUN_SYSTEM = (
    "You fix pronouns in meeting notes. For each numbered line, replace every gendered pronoun "
    "(he, she, him, his, her, hers, himself, herself) with the person's name or with they/them/their, "
    "and fix verb agreement (\"he is\" -> \"they are\"). Change nothing else. Answer with a JSON array of "
    "strings, one per input line, in the same order."
)


def _strings(node, path=()):
    """Yield (path, text) for every string inside a dumped model."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            # ids, names, dates and project names are data, not prose
            if k.endswith(("_id", "_ids", "name", "due_date")) or k == "project":
                continue
            yield from _strings(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, path + (i,))


def _set(node, path, value):
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


async def neutralise_pronouns(analysis: MeetingAnalysis) -> MeetingAnalysis:
    data = analysis.model_dump(mode="json")
    hits = [(path, text) for path, text in _strings(data) if _GENDERED.search(text)]
    if not hits:
        return analysis
    lines = "\n".join(f"{i + 1}. {json.dumps(text)}" for i, (_, text) in enumerate(hits))
    try:
        raw = await complete_text(PRONOUN_SYSTEM, lines, max_tokens=2000)
        fixed = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
        if len(fixed) != len(hits) or not all(isinstance(x, str) for x in fixed):
            raise ValueError("wrong shape")
        for (path, _), text in zip(hits, fixed):
            _set(data, path, text)
        return MeetingAnalysis.model_validate(data)
    except (AnalysisError, ValueError) as exc:
        log.warning("Could not rewrite gendered pronouns: %s", exc)
        return analysis


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


async def _analyse_with_gemini(prompt: str) -> MeetingAnalysis:
    """Gemini over its REST API with JSON-schema structured output; the
    response is validated against the same Pydantic model Claude uses."""
    if not settings.GEMINI_API_KEY:
        raise AnalysisError("ANALYSIS_PROVIDER is gemini but GEMINI_API_KEY is not set in .env.")
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": MeetingAnalysis.model_json_schema(),
            "maxOutputTokens": 32768,
        },
    }
    url = GEMINI_URL.format(model=settings.GEMINI_MODEL)
    headers = {"x-goog-api-key": settings.GEMINI_API_KEY, "Content-Type": "application/json"}
    resp = None
    for attempt in range(3):  # retry rate limits and transient server errors
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            if attempt == 2:
                raise AnalysisError("Could not reach the Gemini API. Check the network and reprocess.") from exc
            await asyncio.sleep(2 * (attempt + 1))
            continue
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            await asyncio.sleep(3 * (attempt + 1))
            continue
        break
    if resp.status_code in (401, 403):
        raise AnalysisError("Gemini rejected the API key. Check GEMINI_API_KEY in .env.")
    if resp.status_code == 404:
        raise AnalysisError(f"Gemini model '{settings.GEMINI_MODEL}' was not found. Set GEMINI_MODEL in .env.")
    if resp.status_code == 429:
        raise AnalysisError("Gemini rate limit or quota reached. Reprocess the meeting later.")
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", {}).get("message", "")
        except ValueError:
            msg = resp.text[:200]
        raise AnalysisError(f"Gemini API error {resp.status_code}: {msg}")

    data = resp.json()
    block = (data.get("promptFeedback") or {}).get("blockReason")
    if block:
        raise AnalysisError(f"Gemini blocked the transcript ({block}).")
    candidates = data.get("candidates") or []
    if not candidates:
        raise AnalysisError("Gemini returned no answer.")
    cand = candidates[0]
    finish = cand.get("finishReason")
    if finish == "MAX_TOKENS":
        raise AnalysisError("The analysis was cut off (output limit). Try a shorter meeting or split the transcript.")
    if finish in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        raise AnalysisError(f"Gemini declined to analyse this transcript ({finish}).")
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
    try:
        return MeetingAnalysis.model_validate_json(text)
    except ValidationError as exc:
        log.warning("Gemini output failed validation: %s", exc)
        raise AnalysisError("Gemini returned an analysis in the wrong shape. Reprocess the meeting.") from exc


async def _analyse_with_claude(prompt: str) -> MeetingAnalysis:
    client = _client()
    try:
        response = await client.beta.messages.parse(
            model=settings.ANALYSIS_MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_format=MeetingAnalysis,
            output_config={"effort": settings.ANALYSIS_EFFORT},
            # Server-side refusal fallback: if the model declines, the API
            # re-runs the request on a fallback model within the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as exc:
        raise AnalysisError("Claude rejected the credentials. Set ANTHROPIC_API_KEY in .env.") from exc
    except anthropic.PermissionDeniedError as exc:
        raise AnalysisError("The Anthropic API key lacks permission for this model.") from exc
    except anthropic.BadRequestError as exc:
        raise AnalysisError(f"Claude rejected the request: {exc.message}") from exc
    except anthropic.RateLimitError as exc:
        raise AnalysisError("Claude rate limit reached. Reprocess the meeting in a minute.") from exc
    except anthropic.APIStatusError as exc:
        raise AnalysisError(f"Claude API error {exc.status_code}. Reprocess the meeting later.") from exc
    except anthropic.APIConnectionError as exc:
        raise AnalysisError("Could not reach the Claude API. Check the network and reprocess.") from exc
    except TypeError as exc:  # no credentials resolved at all
        raise AnalysisError("No Anthropic credentials found. Set ANTHROPIC_API_KEY in .env.") from exc

    if response.stop_reason == "refusal":
        raise AnalysisError("Claude declined to analyse this transcript.")
    if response.stop_reason == "max_tokens":
        raise AnalysisError("The analysis was cut off (output limit). Try a shorter meeting or split the transcript.")
    parsed = response.parsed_output
    if parsed is None:
        raise AnalysisError("Claude returned no structured analysis.")
    return parsed


async def complete_text(system: str, prompt: str, max_tokens: int = 4000) -> str:
    """Plain-text answer from the configured provider (used by Ask)."""
    if provider() == "gemini":
        if not settings.GEMINI_API_KEY:
            raise AnalysisError("GEMINI_API_KEY is not set in .env.")
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens * 4},
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(GEMINI_URL.format(model=settings.GEMINI_MODEL), json=body,
                                         headers={"x-goog-api-key": settings.GEMINI_API_KEY})
        except httpx.HTTPError as exc:
            raise AnalysisError("Could not reach the Gemini API.") from exc
        if resp.status_code >= 400:
            raise AnalysisError(f"Gemini API error {resp.status_code}.")
        cands = resp.json().get("candidates") or []
        if not cands:
            raise AnalysisError("Gemini returned no answer.")
        return "".join(p.get("text", "") for p in (cands[0].get("content") or {}).get("parts", []) if not p.get("thought")).strip()

    client = _client()
    try:
        response = await client.beta.messages.create(
            model=settings.ANALYSIS_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIConnectionError as exc:
        raise AnalysisError("Could not reach the Claude API.") from exc
    except anthropic.APIStatusError as exc:
        raise AnalysisError(f"Claude API error {exc.status_code}.") from exc
    except TypeError as exc:
        raise AnalysisError("No Anthropic credentials found.") from exc
    if response.stop_reason == "refusal":
        raise AnalysisError("The model declined to answer.")
    return "".join(b.text for b in response.content if b.type == "text").strip()
