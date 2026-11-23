"""Meeting reports as email (HTML with a plain-text part) and as a Slack message.

Both are drawn from ``reports.meeting_report_data`` so they show what the
in-app report shows, minus empty sections. Everything that came from the
meeting (titles, names, AI notes) is escaped: HTML for email, Slack's
``& < >`` for Slack.
"""
from __future__ import annotations

from html import escape
from typing import Any, Dict, List, Optional

from app.models import Meeting

# Butter and charcoal, the app's palette. Inline styles only: mail clients drop <style>.
INK, MUTED, BUTTER, PAPER, CARD, LINE = "#22201B", "#6B655A", "#FFD95C", "#F9F6EE", "#FFFFFF", "#E7E1D3"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _actions(d: Dict[str, Any]) -> List[str]:
    out = []
    for a in d["actions"]:
        line = a["title"] + (f" - {a['owner']}" if a["owner"] else "") + (f" (due {a['due']})" if a["due"] else "")
        out.append(line)
    return out


def _meeting_sections(d: Dict[str, Any]) -> List[tuple]:
    return [(title, items) for title, items in (
        ("Key points", d["key_points"]),
        ("Decisions", d["decisions"]),
        ("Action items", _actions(d)),
        ("Open questions", d["open_questions"]),
    ) if items]


# ---- plain text ---------------------------------------------------------------

def email_text(d: Dict[str, Any], link: Optional[str] = None) -> str:
    """The text/plain part: readable as is, no Markdown symbols."""
    out = [d["title"], " · ".join(x for x in (d["when_text"], d["kind"]) if x)]
    if d["attendees"]:
        out.append("Attendees: " + ", ".join(d["attendees"]))
    out.append("")
    if d["overview"]:
        out += ["SUMMARY", d["overview"], ""]
    for title, items in _meeting_sections(d):
        out += [title.upper()] + [f"  • {i}" for i in items] + [""]
    if d["people"] or d["hidden"]:
        out += ["UPDATES BY PERSON", ""]
        for p in d["people"]:
            out.append(p["name"])
            if p["summary"]:
                out.append(p["summary"])
            for label, items in p["sections"]:
                out.append(f"  {label}:")
                out += [f"    • {i}" for i in items]
            if p["review"]:
                out.append(f"  {p['review']}")
            out.append("")
        if d["hidden"]:
            out += [f"{d['hidden']} individual update(s) not shared with you.", ""]
    if d["progress"]:
        out += ["PROGRESS TRACKING", d["progress"], ""]
    if link:
        out += [f"Open the full report: {link}", ""]
    out.append("Sent by MeetPact")
    return "\n".join(out) + "\n"


# ---- HTML -------------------------------------------------------------------

def _h(text: str) -> str:
    return (f'<h2 style="margin:24px 0 8px;font-size:13px;letter-spacing:.06em;text-transform:uppercase;'
            f'color:{MUTED};font-weight:700">{escape(text)}</h2>')


def _ul(items: List[str]) -> str:
    lis = "".join(f'<li style="margin:0 0 6px">{escape(i)}</li>' for i in items)
    return f'<ul style="margin:0;padding:0 0 0 20px;font-size:15px;line-height:1.5;color:{INK}">{lis}</ul>'


def _person(p: Dict[str, Any]) -> str:
    rows = []
    for label, items in p["sections"]:
        rows.append(
            f'<p style="margin:12px 0 4px;font-size:13px;font-weight:700;color:{INK}">{escape(label)}</p>' + _ul(items))
    summary = (f'<p style="margin:6px 0 0;font-size:15px;line-height:1.5;color:{INK}">{escape(p["summary"])}</p>'
               if p["summary"] else "")
    review = (f'<p style="margin:10px 0 0;font-size:13px;color:{MUTED};font-style:italic">{escape(p["review"])}</p>'
              if p["review"] else "")
    return (f'<div style="margin:0 0 12px;padding:16px 18px;background:{PAPER};border:1px solid {LINE};'
            f'border-radius:10px"><p style="margin:0;font-size:16px;font-weight:700;color:{INK}">'
            f'{escape(p["name"])}</p>{summary}{"".join(rows)}{review}</div>')


def email_html(d: Dict[str, Any], link: Optional[str] = None) -> str:
    meta = " · ".join(x for x in (d["when_text"], d["kind"]) if x)
    body = []
    if d["attendees"]:
        body.append(f'<p style="margin:0 0 4px;font-size:14px;color:{MUTED}"><strong style="color:{INK}">Attendees:'
                    f'</strong> {escape(", ".join(d["attendees"]))}</p>')
    if d["overview"]:
        body.append(_h("Summary") + f'<p style="margin:0;font-size:15px;line-height:1.6;color:{INK}">'
                    f'{escape(d["overview"])}</p>')
    for title, items in _meeting_sections(d):
        body.append(_h(title) + _ul(items))
    if d["people"] or d["hidden"]:
        body.append(_h("Updates by person") + "".join(_person(p) for p in d["people"]))
        if d["hidden"]:
            body.append(f'<p style="margin:0;font-size:13px;color:{MUTED}">{d["hidden"]} individual update(s) '
                        f'not shared with you.</p>')
    if d["progress"]:
        body.append(_h("Progress tracking") + f'<p style="margin:0;font-size:15px;color:{INK}">'
                    f'{escape(d["progress"])}</p>')
    button = (f'<p style="margin:28px 0 0"><a href="{escape(link, quote=True)}" style="display:inline-block;'
              f'padding:12px 20px;background:{BUTTER};color:{INK};font-weight:700;font-size:15px;'
              f'text-decoration:none;border:2px solid {INK};border-radius:10px">Open the full report</a></p>'
              if link else "")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(d["title"])}</title></head>
<body style="margin:0;padding:0;background:{PAPER};font-family:{FONT}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;background:{CARD};border:2px solid {INK};border-radius:14px">
<tr><td style="padding:20px 24px;background:{BUTTER};border-bottom:2px solid {INK};border-radius:12px 12px 0 0">
<p style="margin:0 0 4px;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:{INK}">MeetPact · Meeting notes</p>
<h1 style="margin:0;font-size:22px;line-height:1.3;color:{INK}">{escape(d["title"])}</h1>
<p style="margin:6px 0 0;font-size:14px;color:{INK}">{escape(meta)}</p>
</td></tr>
<tr><td style="padding:20px 24px 28px">{"".join(body)}{button}</td></tr>
</table>
<p style="margin:16px 0 0;font-size:12px;color:{MUTED}">Sent by MeetPact. You get this because the report is shared with you.</p>
</td></tr></table>
</body></html>
"""


# ---- Slack ------------------------------------------------------------------

def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _when_kind(meeting: Meeting) -> str:
    from app.services.reports import MODE_LABELS

    when = meeting.started_at or meeting.scheduled_at or meeting.created_at
    parts = [f"{when:%a %d %b, %H:%M} UTC" if when else "", MODE_LABELS.get(meeting.mode or "", "")]
    attendees = [p for p in (meeting.participants or []) if not p.is_bot]
    if attendees:
        parts.append(f"{len(attendees)} attendee" + ("" if len(attendees) == 1 else "s"))
    return " · ".join(p for p in parts if p)


def _slack_lists(meeting: Meeting) -> List[tuple]:
    s = meeting.summary or {}
    actions = []
    for a in (s.get("action_items") or [])[:8]:
        if isinstance(a, dict) and (a.get("title") or "").strip():
            line = _slack_escape(a["title"].strip())
            if a.get("owner_name"):
                line += f" - *{_slack_escape(a['owner_name'])}*"
            if a.get("due_date"):
                line += f" _(due {_slack_escape(str(a['due_date']))})_"
            actions.append(line)
    decisions = [_slack_escape(str(x).strip()) for x in (s.get("decisions") or [])[:5] if str(x or "").strip()]
    return [(t, items) for t, items in (("Decisions", decisions), ("Action items", actions)) if items]


def slack_text(meeting: Meeting, link: Optional[str] = None) -> str:
    """Fallback text, shown in notifications and where blocks can't be."""
    s = meeting.summary or {}
    lines = [f"*{_slack_escape(meeting.title)}* - meeting notes are ready", _slack_escape(s.get("overview") or "")]
    for title, items in _slack_lists(meeting):
        lines.append(f"*{title}*\n" + "\n".join(f"• {i}" for i in items))
    if link:
        lines.append(f"<{link}|Open the full report>")
    return "\n\n".join(l for l in lines if l)


def slack_payload(meeting: Meeting, link: Optional[str] = None) -> Dict[str, Any]:
    """An incoming-webhook message: Block Kit layout plus the text fallback."""
    s = meeting.summary or {}
    blocks: List[Dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": meeting.title[:150], "emoji": True}},
    ]
    meta = _when_kind(meeting)
    if meta:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": _slack_escape(meta)}]})
    if s.get("overview"):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _slack_escape(s["overview"])[:2900]}})
    for title, items in _slack_lists(meeting):
        blocks.append({"type": "section", "text": {
            "type": "mrkdwn", "text": (f"*{title}*\n" + "\n".join(f"• {i}" for i in items))[:2900]}})
    if link:
        blocks.append({"type": "actions", "elements": [{
            "type": "button", "style": "primary", "url": link,
            "text": {"type": "plain_text", "text": "Open the full report"}}]})
    return {"text": slack_text(meeting, link), "blocks": blocks}
