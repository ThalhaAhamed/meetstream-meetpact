"""Recurrence rules for schedules: once, daily, weekdays, weekly(days)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterator, List
from zoneinfo import ZoneInfo

from app.models import Schedule


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def occurs_on(schedule: Schedule, day: date) -> bool:
    if day < schedule.start_date or (schedule.end_date and day > schedule.end_date):
        return False
    rule = schedule.recurrence
    if rule == "once":
        return day == schedule.start_date
    if rule == "daily":
        return True
    if rule == "weekdays":
        return day.weekday() < 5
    if rule == "weekly":
        days = schedule.days_of_week or [schedule.start_date.weekday()]
        return day.weekday() in days
    return False


def occurrences(schedule: Schedule, start: datetime, end: datetime) -> Iterator[datetime]:
    """UTC datetimes of occurrences with start <= t < end."""
    tz = _tz(schedule.timezone)
    hh, mm = (int(x) for x in schedule.time_of_day.split(":"))
    local_start = start.astimezone(tz).date() - timedelta(days=1)
    local_end = end.astimezone(tz).date() + timedelta(days=1)
    day = local_start
    while day <= local_end:
        if occurs_on(schedule, day):
            t = datetime.combine(day, time(hh, mm), tzinfo=tz).astimezone(timezone.utc)
            if start <= t < end:
                yield t
        day += timedelta(days=1)


def upcoming(schedule: Schedule, days: int = 7, limit: int = 20) -> List[datetime]:
    now = datetime.now(timezone.utc)
    out = []
    for t in occurrences(schedule, now, now + timedelta(days=days)):
        out.append(t)
        if len(out) >= limit:
            break
    return out


def local_date(schedule_tz: str, t: datetime) -> date:
    return t.astimezone(_tz(schedule_tz)).date()


def occurrence_key(schedule_id: str, t: datetime) -> str:
    return f"{schedule_id}:{t.strftime('%Y%m%dT%H%M')}"
