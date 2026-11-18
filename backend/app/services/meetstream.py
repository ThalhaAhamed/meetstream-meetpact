"""MeetStream REST client.

Only documented endpoints are used (see meetstream-ai/meetstream-python and
meetstream-ai/labs). Behaviours worth knowing, all handled here:

* Auth is ``Authorization: Token <key>``.
* ``202`` means "not ready yet" (transcripts, chats) - raised as NotReady.
* ``507`` on create_bot is an idempotent replay and counts as success.
* ``remove_bot`` is a GET.
* ``video_required`` defaults to true on the API, so it is always sent.
* Transcripts are keyed by transcript_id, not bot_id.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

log = logging.getLogger(__name__)


class MeetStreamError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class NotReady(MeetStreamError):
    """HTTP 202: the resource exists but is still being produced."""


class NotConfigured(MeetStreamError):
    pass


def _friendly(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        detail = body.get("detail") or body.get("message") or body.get("error") or body
    except Exception:
        detail = resp.text[:300]
    if resp.status_code == 401:
        return "MeetStream did not receive an API key. Set MEETSTREAM_API_KEY in .env."
    if resp.status_code == 403:
        return "MeetStream rejected the API key. Check MEETSTREAM_API_KEY."
    if resp.status_code == 429:
        return "MeetStream rate limit reached. Try again in a minute."
    return f"MeetStream returned {resp.status_code}: {detail}"


class MeetStreamClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self._api_key = api_key
        self._base_url = base_url

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key or settings.MEETSTREAM_API_KEY

    @property
    def base_url(self) -> str:
        return (self._base_url or settings.MEETSTREAM_BASE_URL).rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        if not self.api_key:
            raise NotConfigured("MEETSTREAM_API_KEY is not set, so no bot can be sent. Add it to .env and restart.")
        hdrs = {"Authorization": f"Token {self.api_key}", "Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method, f"{self.base_url}{path}", json=json, params=params, headers=hdrs)
        except httpx.TimeoutException as exc:
            raise MeetStreamError("MeetStream did not answer in time. Try again in a moment.") from exc
        except httpx.HTTPError as exc:
            raise MeetStreamError(f"Could not reach MeetStream ({exc.__class__.__name__}). Check the network.") from exc
        if resp.status_code == 202:
            raise NotReady("Not ready yet", status=202)
        if resp.status_code == 507:  # idempotent replay of create_bot
            return resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise MeetStreamError(_friendly(resp), status=resp.status_code)
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    # ---- bots ---------------------------------------------------------------

    async def create_bot(self, payload: Dict[str, Any], idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return await self._request("POST", "/bots/create_bot", json=payload, headers=headers, timeout=45.0)

    async def status(self, bot_id: str) -> str:
        body = await self._request("GET", f"/bots/{bot_id}/status", timeout=15.0)
        if isinstance(body, dict):
            return str(body.get("status") or body.get("bot_status") or "")
        return str(body or "")

    async def detail(self, bot_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/bots/{bot_id}/detail", timeout=15.0)

    async def transcriptions(self, bot_id: str) -> List[Dict[str, Any]]:
        body = await self._request("GET", f"/bots/{bot_id}/transcriptions", timeout=15.0)
        if isinstance(body, dict):
            return body.get("transcriptions") or []
        return body or []

    async def participants(self, bot_id: str) -> List[Dict[str, Any]]:
        body = await self._request("GET", f"/bots/{bot_id}/get_participants", timeout=15.0)
        if isinstance(body, dict):
            for key in ("participants", "data", "results"):
                if isinstance(body.get(key), list):
                    return body[key]
            return []
        return body or []

    async def chats(self, bot_id: str) -> Any:
        return await self._request("GET", f"/bots/{bot_id}/get_chats", timeout=15.0)

    async def send_message(self, bot_id: str, message: str) -> Dict[str, Any]:
        return await self._request("POST", f"/bots/{bot_id}/send_message", json={"message": message}, timeout=15.0)

    async def pause_recording(self, bot_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/bots/{bot_id}/pause_recording", json={}, timeout=15.0)

    async def resume_recording(self, bot_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/bots/{bot_id}/resume_recording", json={}, timeout=15.0)

    async def remove_bot(self, bot_id: str) -> Dict[str, Any]:
        # MeetStream answers once the bot has actually left, which can take a while.
        return await self._request("GET", f"/bots/{bot_id}/remove_bot", timeout=60.0)

    async def cancel_scheduled_bot(self, bot_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/calendar/scheduled_bots/{bot_id}", timeout=15.0)

    async def reschedule_bot(self, bot_id: str, join_at_iso: str) -> Dict[str, Any]:
        return await self._request(
            "PATCH", f"/calendar/scheduled_bots/{bot_id}", json={"scheduled_join_time": join_at_iso}, timeout=15.0
        )

    # ---- transcripts --------------------------------------------------------

    async def get_transcript(self, transcript_id: str) -> Any:
        return await self._request(
            "GET", f"/transcript/{transcript_id}/get_transcript", params={"raw": "false"}, timeout=60.0
        )

    # ---- calendar ----------------------------------------------------------

    async def connect_google_calendar(self, client_id: str, client_secret: str, refresh_token: str) -> Dict[str, Any]:
        # Field names need the google_ prefix; plain client_id etc. are rejected.
        body = {"google_client_id": client_id, "google_client_secret": client_secret, "google_refresh_token": refresh_token}
        return await self._request("POST", "/calendar/create_calendar", json=body, timeout=60.0)

    async def connect_outlook_calendar(self, client_id: str, client_secret: str, refresh_token: str) -> Dict[str, Any]:
        body = {"microsoft_client_id": client_id, "microsoft_client_secret": client_secret,
                "microsoft_refresh_token": refresh_token, "replace": True}
        return await self._request("POST", "/calendar/create_outlook_calendar", json=body, timeout=60.0)

    async def list_calendars(self) -> List[Dict[str, Any]]:
        body = await self._request("GET", "/calendar/calendars", timeout=30.0)
        return (body.get("calendars") if isinstance(body, dict) else body) or []

    async def calendar_events(self, max_pages: int = 5) -> List[Dict[str, Any]]:
        """Upcoming synced events. The endpoint is paginated with a `next` link."""
        events: List[Dict[str, Any]] = []
        path: Optional[str] = "/calendar/events"
        for _ in range(max_pages):
            body = await self._request("GET", path, timeout=60.0)
            if isinstance(body, list):
                return events + body
            events.extend(body.get("results") or [])
            nxt = body.get("next")
            if not body.get("has_more") or not nxt:
                break
            path = nxt.split("/api/v1", 1)[-1] if "/api/v1" in nxt else nxt
        return events

    async def disconnect_calendar(self) -> Dict[str, Any]:
        return await self._request("DELETE", "/calendar/disconnect", timeout=60.0)

    async def delete_bot_data(self, bot_id: str) -> Dict[str, Any]:
        """Permanently delete the bot's audio, video and transcript at MeetStream."""
        return await self._request("DELETE", f"/bots/{bot_id}/delete", timeout=60.0)

    # ---- MIA agents (stand-up mode) ----------------------------------------

    async def create_mia_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/mia", json=payload, timeout=30.0)

    async def delete_mia_agent(self, agent_config_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", "/mia", params={"agent_config_id": agent_config_id}, timeout=15.0)


meetstream = MeetStreamClient()


# MeetStream's lifecycle states, mapped to this app's.
REMOTE_STATUS = {
    "scheduled": "scheduled",
    "joining": "joining",
    "inwaitingroom": "waiting_room",
    "inmeeting": "in_meeting",
    "recording": "recording",
    "leaving": "ended",
    "stopped": "ended",
    "kicked": "ended",
    "mediaprocessing": "ended",
    "done": "ended",
    "notallowed": "not_admitted",
    "denied": "denied",
    "failed": "failed",
    "error": "failed",
}

LIVE_STATES = {"joining", "waiting_room", "in_meeting", "recording", "paused"}
IN_CALL_STATES = {"in_meeting", "recording", "paused"}
FINISHED_STATES = {"ended", "not_admitted", "denied", "failed", "cancelled"}


def map_remote_status(remote: str) -> Optional[str]:
    return REMOTE_STATUS.get((remote or "").replace("_", "").replace(" ", "").lower())


STOP_REASONS = {
    "bot.stopped": ("ended", "The bot left normally."),
    "bot.kicked": ("ended", "A participant removed the bot from the meeting."),
    "bot.notallowed": ("not_admitted", "Nobody admitted the bot from the waiting room before it timed out."),
    "bot.denied": ("denied", "A host refused the bot or refused recording. Not retried."),
    "bot.failed": ("failed", "The bot session failed. Send a new bot."),
}


def stop_reason(event: Dict[str, Any]) -> str:
    reason = event.get("bot_event")
    if isinstance(reason, str) and reason:
        return reason
    status = str(event.get("bot_status") or "").lower()
    if status == "notallowed":
        return "bot.notallowed"
    if status == "denied":
        return "bot.denied"
    if status in ("error", "failed"):
        return "bot.failed"
    return "bot.stopped"
