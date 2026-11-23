"""Deliver the meeting report after it is generated: email and Slack.

Both are optional and respect report sharing:
* Email goes to each user allowed to see the full report, and each gets the
  version of the report they are allowed to see (individual updates filtered
  by the employee-update sharing setting).
* Email is HTML (with a plain-text part); Slack is a Block Kit message.
* Slack gets a short summary and a link, and only when the full report is
  shared with participants or managers - a channel is too wide an audience
  for an organizer-only or selected-people report.
A report is delivered once; re-analysing a meeting does not send it again.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Dict, List

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import access
from app.config import settings
from app.models import Meeting, User
from app.services.app_settings import get_setting
from app.services import report_formats
from app.services.reports import meeting_report_data

log = logging.getLogger(__name__)


def email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM)


def slack_configured() -> bool:
    return bool(settings.SLACK_WEBHOOK_URL)


def meeting_url(meeting: Meeting) -> str:
    return f"{settings.APP_URL.rstrip('/')}/meetings/{meeting.id}"


# Reserved/example domains never receive mail; sending to them only bounces.
UNDELIVERABLE = (".local", ".localhost", ".test", ".example", ".invalid", "@example.com", "@example.org")


def deliverable(email: str | None) -> bool:
    return bool(email) and "@" in email and not email.lower().endswith(UNDELIVERABLE)


def report_link(meeting: Meeting) -> str | None:
    """A link back to the report, only when APP_URL is an address others can open."""
    return meeting_url(meeting) if settings.app_url_is_public else None


def recipients(db: Session, meeting: Meeting) -> List[User]:
    return [u for u in db.scalars(select(User)) if deliverable(u.email) and access.can_view_full(db, u, meeting)]


def _send_email(to: str, subject: str, body: str, html: str | None = None) -> None:
    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    # Port 465 is implicit TLS (SMTP_SSL); 587/25 upgrade with STARTTLS.
    if settings.SMTP_PORT == 465:
        conn = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)
    else:
        conn = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)
    with conn as smtp:
        if settings.SMTP_PORT != 465 and settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
        smtp.send_message(msg)


def slack_text(meeting: Meeting) -> str:
    return report_formats.slack_text(meeting, report_link(meeting))


def slack_payload(meeting: Meeting) -> dict:
    return report_formats.slack_payload(meeting, report_link(meeting))


async def send_test(channel: str, to_email: str | None) -> str:
    """Send a test message so an admin can check the setup. Raises ValueError
    with a readable reason on failure."""
    if channel == "email":
        if not email_configured():
            raise ValueError("Email is not set up: set SMTP_HOST and SMTP_FROM in .env and restart.")
        if not to_email:
            raise ValueError("Your account has no email address to send the test to.")
        try:
            await asyncio.to_thread(_send_email, to_email, "MeetPact test email",
                                    "This is a test from MeetPact. Meeting reports will arrive like this.\n\n"
                                    + (f"Open MeetPact: {settings.APP_URL}\n" if settings.app_url_is_public else ""))
        except smtplib.SMTPAuthenticationError:
            raise ValueError("The mail server rejected the login. For Gmail, SMTP_PASSWORD must be an app password.")
        except (OSError, smtplib.SMTPException) as exc:
            raise ValueError(f"Sending failed: {exc.__class__.__name__}: {str(exc)[:200]}")
        return f"Test email sent to {to_email}."
    if channel == "slack":
        if not slack_configured():
            raise ValueError("Slack is not set up: set SLACK_WEBHOOK_URL in .env and restart.")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(settings.SLACK_WEBHOOK_URL, json={
                    "text": "*MeetPact test* - meeting reports will be posted here."
                            + (f" <{settings.APP_URL}|Open MeetPact>" if settings.app_url_is_public else "")})
        except httpx.HTTPError as exc:
            raise ValueError(f"Could not reach Slack ({exc.__class__.__name__}).")
        if r.status_code >= 400:
            raise ValueError(f"Slack answered {r.status_code}: {r.text[:200]}")
        return "Test message posted to Slack."
    raise ValueError("Unknown channel.")


async def deliver(db: Session, meeting: Meeting) -> Dict[str, int]:
    """Send the report once. Returns counts for the log."""
    sent = {"emails": 0, "slack": 0}
    if meeting.report_delivered_at or meeting.processing_status != "done":
        return sent
    if get_setting(db, "deliver_email") and email_configured():
        for user in recipients(db, meeting):
            data = meeting_report_data(db, meeting, lambda eid, u=user: access.can_view_employee_section(db, u, meeting, eid))
            link = report_link(meeting)
            try:
                await asyncio.to_thread(_send_email, user.email, f"Meeting notes: {meeting.title}",
                                        report_formats.email_text(data, link), report_formats.email_html(data, link))
                sent["emails"] += 1
            except (OSError, smtplib.SMTPException) as exc:
                log.warning("Report email to a recipient failed: %s", exc.__class__.__name__)
    audience = (meeting.share_full or {}).get("audience")
    if get_setting(db, "deliver_slack") and slack_configured() and audience in ("participants", "managers"):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(settings.SLACK_WEBHOOK_URL, json=slack_payload(meeting))
            if r.status_code < 400:
                sent["slack"] = 1
            else:
                log.warning("Slack webhook returned %s", r.status_code)
        except httpx.HTTPError as exc:
            log.warning("Slack delivery failed: %s", exc.__class__.__name__)
    if sent["emails"] or sent["slack"]:
        meeting.report_delivered_at = datetime.now(timezone.utc)
        db.commit()
    return sent
