"""Map meeting display names to employee records."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Employee

_NOISE = re.compile(r"\((?:guest|host|me|you|external|presenter)\)|\s+-\s+.*$", re.I)


def norm(name: str) -> str:
    name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    name = _NOISE.sub("", name)
    return re.sub(r"[^a-z0-9 ]+", " ", name.lower()).strip()


def is_bot_name(name: str) -> bool:
    n = norm(name)
    return bool(n) and (n == norm(settings.BOT_NAME) or "notetaker" in n or n.endswith(" bot"))


def match_employee(name: str, employees: Iterable[Employee]) -> Optional[Employee]:
    """Best-effort match: exact name/alias/email-local-part, then unique first
    name, then unique 'first + last initial'. Returns None when ambiguous."""
    target = norm(name)
    if not target:
        return None
    employees = list(employees)
    for e in employees:
        candidates = [e.name, *(e.aliases or [])]
        if e.email:
            candidates.append(e.email.split("@")[0].replace(".", " "))
        if target in {norm(c) for c in candidates if c}:
            return e
    tokens = target.split()
    if not tokens:
        return None
    first = tokens[0]
    by_first = [e for e in employees if norm(e.name).split()[:1] == [first]]
    if len(tokens) == 1 and len(by_first) == 1:
        return by_first[0]
    if len(tokens) >= 2 and by_first:
        initial = tokens[1][0]
        narrowed = [e for e in by_first if len(norm(e.name).split()) > 1 and norm(e.name).split()[1].startswith(initial)]
        if len(narrowed) == 1:
            return narrowed[0]
        if len(by_first) == 1:
            return by_first[0]
    return None


def active_employees(db: Session) -> List[Employee]:
    return list(db.scalars(select(Employee).where(Employee.active.is_(True))))
