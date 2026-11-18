"""The post-call pipeline: transcript -> speakers -> consent -> Claude -> records -> report."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Meeting, Project, TranscriptSegment
from app.services import consent, identity, tracker
from app.services.extraction import AnalysisError, analyse_meeting, build_prompt
from app.services.meetstream import MeetStreamError, NotReady, meetstream
from app.services.reports import render_meeting_report
from app.services.transcript import normalize_transcript, render_transcript

log = logging.getLogger(__name__)

TRANSCRIPT_WAIT = timedelta(hours=6)  # how long after the call to keep waiting for MeetStream


async def find_transcript_id(meeting: Meeting) -> Optional[str]:
    if meeting.transcript_id:
        return meeting.transcript_id
    if not meeting.bot_id:
        return None
    try:
        detail = await meetstream.detail(meeting.bot_id)
        bd = detail.get("bot_details", detail) if isinstance(detail, dict) else {}
        tid = bd.get("transcript_id") if isinstance(bd, dict) else None
        if tid:
            return str(tid)
    except MeetStreamError:
        pass
    try:
        runs = await meetstream.transcriptions(meeting.bot_id)
        for run in runs:
            tid = run.get("transcript_id") or run.get("id")
            if tid:
                return str(tid)
    except MeetStreamError:
        pass
    return None


async def fetch_turns(db: Session, meeting: Meeting) -> Optional[List[Dict[str, Any]]]:
    """Return speaker turns, or None if MeetStream has not produced them yet."""
    tid = await find_transcript_id(meeting)
    if not tid:
        return None
    meeting.transcript_id = tid
    try:
        payload = await meetstream.get_transcript(tid)
    except NotReady:
        return None
    return normalize_transcript(payload)


def store_turns(db: Session, meeting: Meeting, turns: List[Dict[str, Any]]) -> None:
    for seg in list(meeting.segments):
        db.delete(seg)
    db.flush()
    employees = identity.active_employees(db)
    for i, t in enumerate(turns):
        p, _ = consent.upsert_participant(db, meeting, t["speaker"], employees, from_roster=False)
        meeting.segments.append(
            TranscriptSegment(
                meeting_id=meeting.id,
                position=i,
                speaker=t["speaker"],
                employee_id=p.employee_id,
                text=t["text"],
                start_seconds=t.get("start"),
                end_seconds=t.get("end"),
            )
        )
    db.flush()


def rematch_participants(db: Session, meeting: Meeting) -> None:
    """Link still-unmatched speakers to employees added since they were first
    seen (e.g. a profile created after the call). Manual choices are kept."""
    employees = identity.active_employees(db)
    for p in meeting.participants:
        if p.mapping == "unmatched" and not p.is_bot:
            emp = identity.match_employee(p.display_name, employees)
            if emp:
                p.employee_id, p.mapping = emp.id, "auto"
                for seg in meeting.segments:
                    if seg.speaker == p.display_name:
                        seg.employee_id = emp.id
    db.flush()


async def analyse_and_apply(db: Session, meeting: Meeting) -> None:
    rematch_participants(db, meeting)
    turns = [
        {"speaker": s.speaker, "text": s.text, "start": s.start_seconds}
        for s in meeting.segments
        if not s.redacted
    ]
    if not turns:
        raise AnalysisError("The transcript is empty, so there is nothing to analyse.")
    # Label speakers with their employee names so the model sees one identity.
    names = {p.display_name: (p.employee.name if p.employee else p.display_name) for p in meeting.participants}
    for t in turns:
        mapped = names.get(t["speaker"])
        if mapped and mapped != t["speaker"]:
            t["speaker"] = f"{mapped} (shown as {t['speaker']})"
    attendee_ids = sorted({p.employee_id for p in meeting.participants if p.employee_id})
    prompt = build_prompt(
        title=meeting.title,
        meeting_date=meeting.meeting_date,
        slot=meeting.slot,
        mode=meeting.mode,
        roster=tracker.roster_context(db, meeting, attendee_ids),
        projects=[p.name for p in db.scalars(select(Project).where(Project.status == "active"))],
        transcript=render_transcript(turns),
    )
    meeting.processing_status = "analysing"
    db.commit()

    analysis = await analyse_meeting(prompt)

    stats = tracker.apply_analysis(db, meeting, analysis)
    data = analysis.model_dump()
    data["stats"] = stats
    meeting.summary = data
    meeting.report_md = render_meeting_report(db, meeting)
    meeting.processing_status = "done"
    meeting.processing_error = None
    db.commit()
    log.info("Processed meeting %s: %s", meeting.id, stats)

    from app.services.integrations import auto_push_new_items

    await auto_push_new_items(db, meeting)

    from app.services.delivery import deliver

    try:
        await deliver(db, meeting)
    except Exception:  # delivery problems never fail the meeting
        log.exception("Report delivery failed for %s", meeting.id)


async def process_meeting(meeting_id: str, turns: Optional[List[Dict[str, Any]]] = None) -> str:
    """Run the pipeline. Returns the final processing_status.

    With ``turns`` (imported transcript) MeetStream is not called."""
    with session_scope() as db:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            return "missing"
        try:
            if turns is None and not meeting.segments:
                meeting.processing_status = "fetching"
                db.commit()
                fetched = await fetch_turns(db, meeting)
                if fetched is None:
                    meeting.transcript_attempts += 1
                    # Give up by elapsed time since the call ended, not by poll
                    # count: long meetings can take a long time to transcribe.
                    ended = meeting.ended_at or meeting.created_at
                    if ended.tzinfo is None:
                        ended = ended.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) - ended > TRANSCRIPT_WAIT:
                        meeting.processing_status = "failed"
                        meeting.processing_error = (
                            "MeetStream never produced a transcript for this bot. If the transcription provider "
                            "is streaming-only there is no post-call transcript; import the transcript instead."
                        )
                    else:
                        meeting.processing_status = "waiting"
                    db.commit()
                    return meeting.processing_status
                store_turns(db, meeting, fetched)
            elif turns is not None:
                store_turns(db, meeting, turns)
            await analyse_and_apply(db, meeting)
        except (AnalysisError, MeetStreamError) as exc:
            db.rollback()
            meeting = db.get(Meeting, meeting_id)
            meeting.processing_status = "failed"
            meeting.processing_error = str(exc)
            db.commit()
            log.warning("Processing failed for %s: %s", meeting_id, exc)
        except Exception as exc:  # keep the meeting in a truthful state
            log.exception("Unexpected processing failure for %s", meeting_id)
            db.rollback()
            meeting = db.get(Meeting, meeting_id)
            meeting.processing_status = "failed"
            meeting.processing_error = f"Unexpected error: {exc.__class__.__name__}. See server logs."
            db.commit()
        return meeting.processing_status
