"""Database models.

The core idea: a meeting produces *updates* (what each person said about
their work in that meeting) and those updates move long-lived *work items*
(the commitments, tasks and blockers that persist across meetings). The
work-item history is what turns a notetaker into a progress tracker.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

class User(Base):
    """A login. Roles: admin (everything), manager, employee."""

    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="employee")
    employee_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    employee: Mapped[Optional["Employee"]] = relationship(foreign_keys=[employee_id])


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    # use_alter: teams <-> employees reference each other.
    lead_employee_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL", use_alter=True, name="fk_team_lead"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    team_id: Mapped[Optional[str]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | paused | done
    # Words that identify this project in conversation, so work items can be
    # attributed to it ("billing", "the mobile app", "ACME-portal").
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    team_id: Mapped[Optional[str]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    # Other names this person shows up as in meetings ("Sam K", "samk-laptop").
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    team: Mapped[Optional[Team]] = relationship(foreign_keys=[team_id])


class EmployeeProject(Base):
    __tablename__ = "employee_projects"
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)


# ---------------------------------------------------------------------------
# Scheduling and meetings
# ---------------------------------------------------------------------------

class Schedule(Base):
    """A recurring (or one-off) meeting the bot should attend."""

    __tablename__ = "schedules"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255))
    meeting_link: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20), default="notetaker")  # notetaker | standup
    slot: Mapped[str] = mapped_column(String(20), default="general")  # unused label, kept for older databases
    recurrence: Mapped[str] = mapped_column(String(20), default="weekly")  # once | daily | weekdays | weekly
    days_of_week: Mapped[list] = mapped_column(JSON, default=list)  # 0=Mon .. 6=Sun, for weekly
    time_of_day: Mapped[str] = mapped_column(String(5))  # "09:30", local to timezone
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    team_id: Mapped[Optional[str]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    organizer_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    share_full: Mapped[dict] = mapped_column(JSON, default=dict)
    share_employee: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Meeting(Base):
    __tablename__ = "meetings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255))
    meeting_link: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(20), default="notetaker")
    slot: Mapped[str] = mapped_column(String(20), default="general")
    schedule_id: Mapped[Optional[str]] = mapped_column(ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True, index=True)
    occurrence_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    team_id: Mapped[Optional[str]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    organizer_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # The calendar day this meeting counts towards (for daily reports).
    meeting_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)

    # MeetStream
    bot_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    transcript_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    mia_agent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    bot_status: Mapped[str] = mapped_column(String(40), default="pending")
    # pending | scheduled | joining | waiting_room | in_meeting | recording | paused
    # | ended | not_admitted | denied | failed | cancelled | imported
    stop_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Processing
    processing_status: Mapped[str] = mapped_column(String(20), default="waiting")
    # waiting | fetching | analysing | done | failed | skipped
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_attempts: Mapped[int] = mapped_column(Integer, default=0)

    # Output
    summary: Mapped[dict] = mapped_column(JSON, default=dict)  # overview, key_points, decisions, ...
    report_md: Mapped[str] = mapped_column(Text, default="")

    # Consent
    consent_notice_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    recording_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set once the report has been emailed / posted, so re-analysis does not resend it.
    report_delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # When the transcript (here) and the recording (at MeetStream) were deleted.
    media_deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Sharing: {"audience": "organizer|participants|managers|selected", "user_ids": [...]}
    share_full: Mapped[dict] = mapped_column(JSON, default=dict)
    share_employee: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    participants: Mapped[list["MeetingParticipant"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="MeetingParticipant.first_seen_at"
    )
    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="TranscriptSegment.position"
    )


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"
    __table_args__ = (UniqueConstraint("meeting_id", "display_name"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    employee_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    mapping: Mapped[str] = mapped_column(String(20), default="unmatched")  # auto | manual | unmatched
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_late: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)

    meeting: Mapped[Meeting] = relationship(back_populates="participants")
    employee: Mapped[Optional[Employee]] = relationship()


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(255))
    employee_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    start_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    end_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    redacted: Mapped[bool] = mapped_column(Boolean, default=False)

    meeting: Mapped[Meeting] = relationship(back_populates="segments")


class ConsentEvent(Base):
    """Audit trail of everything the bot did to inform people and honour consent."""

    __tablename__ = "consent_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    # activity log: notice_sent | paused | resumed | removed | denied | data_deleted
    participant: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(255), default="bot")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

class EmployeeUpdate(Base):
    """What one person reported in one meeting."""

    __tablename__ = "employee_updates"
    __table_args__ = (UniqueConstraint("meeting_id", "employee_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    slot: Mapped[str] = mapped_column(String(20), default="general")
    meeting_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    completed: Mapped[list] = mapped_column(JSON, default=list)
    in_progress: Mapped[list] = mapped_column(JSON, default=list)
    planned: Mapped[list] = mapped_column(JSON, default=list)
    pending: Mapped[list] = mapped_column(JSON, default=list)
    blockers: Mapped[list] = mapped_column(JSON, default=list)
    commitments: Mapped[list] = mapped_column(JSON, default=list)  # [{"text":..., "due": "YYYY-MM-DD"|None}]
    # Review by the employee: unreviewed | confirmed | corrected
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed")
    employee_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    employee: Mapped[Employee] = relationship()
    meeting: Mapped[Meeting] = relationship()


class WorkItem(Base):
    """A task / commitment tracked across meetings until it is done."""

    __tablename__ = "work_items"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    employee_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    details: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="task")  # task | action_item | commitment
    status: Mapped[str] = mapped_column(String(20), default="planned", index=True)
    # planned | in_progress | blocked | completed | dropped
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="ai")  # ai | manual
    created_meeting_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    last_meeting_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    carry_count: Mapped[int] = mapped_column(Integer, default=0)  # meetings it was carried forward through
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Task-tool link
    external_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    external_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    external_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    employee: Mapped[Optional[Employee]] = relationship()
    project: Mapped[Optional[Project]] = relationship()
    events: Mapped[list["WorkItemEvent"]] = relationship(
        back_populates="work_item", cascade="all, delete-orphan", order_by="WorkItemEvent.at"
    )


class WorkItemEvent(Base):
    """One change to a work item - the item's history."""

    __tablename__ = "work_item_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    work_item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), index=True)
    meeting_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    # created | status_changed | mentioned | carried_over | due_changed | corrected | synced
    from_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(255), default="ai")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    work_item: Mapped[WorkItem] = relationship(back_populates="events")


class Blocker(Base):
    __tablename__ = "blockers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    employee_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    work_item_id: Mapped[Optional[str]] = mapped_column(ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | resolved
    raised_meeting_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    resolved_meeting_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=1)
    # Last meeting that counted as a mention, so re-analysing it does not count twice.
    last_meeting_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Optional[Employee]] = relationship()


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------

class WebhookDelivery(Base):
    """Idempotency log for MeetStream webhook deliveries."""

    __tablename__ = "webhook_deliveries"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    """Small key/value store for settings editable from the UI."""

    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
