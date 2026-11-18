from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

import httpx


class IntegrationError(Exception):
    pass


@dataclass
class TaskRef:
    id: str
    url: Optional[str]
    status: Optional[str]


class Provider:
    name: str = ""
    label: str = ""
    required_env: List[str] = []

    def configured(self) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    async def create_task(self, *, title: str, description: str, due: Optional[date], assignee_email: Optional[str]) -> TaskRef:
        raise NotImplementedError

    async def fetch_status(self, external_id: str) -> Tuple[str, Optional[str]]:
        """Return (raw external status, mapped local status or None)."""
        raise NotImplementedError

    @staticmethod
    def check(resp: httpx.Response, label: str) -> dict:
        if resp.status_code in (401, 403):
            raise IntegrationError(f"{label} rejected the credentials ({resp.status_code}).")
        if resp.status_code >= 400:
            raise IntegrationError(f"{label} returned {resp.status_code}: {resp.text[:200]}")
        return resp.json() if resp.content else {}


def map_status_text(text: str) -> Optional[str]:
    """Map a free-text status name to a local status."""
    t = (text or "").lower()
    if any(w in t for w in ("done", "complete", "closed", "resolved", "shipped")):
        return "completed"
    if any(w in t for w in ("block", "stuck", "on hold")):
        return "blocked"
    if any(w in t for w in ("progress", "doing", "review", "working")):
        return "in_progress"
    if any(w in t for w in ("to do", "todo", "open", "backlog", "new", "not started")):
        return "planned"
    if any(w in t for w in ("cancel", "won't", "wont")):
        return "dropped"
    return None
