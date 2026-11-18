"""Provider implementations over each tool's public REST API."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Dict, Optional, Tuple

import httpx

from app.config import settings
from app.services.integrations.base import IntegrationError, Provider, TaskRef, map_status_text

TIMEOUT = 20.0


class ClickUp(Provider):
    name, label = "clickup", "ClickUp"
    required_env = ["CLICKUP_API_TOKEN", "CLICKUP_LIST_ID"]
    base = "https://api.clickup.com/api/v2"

    def configured(self) -> bool:
        return bool(settings.CLICKUP_API_TOKEN and settings.CLICKUP_LIST_ID)

    def _h(self):
        return {"Authorization": settings.CLICKUP_API_TOKEN, "Content-Type": "application/json"}

    async def create_task(self, *, title, description, due, assignee_email):
        body: Dict = {"name": title, "description": description}
        if due:
            body["due_date"] = int(datetime(due.year, due.month, due.day, tzinfo=timezone.utc).timestamp() * 1000)
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            data = self.check(await c.post(f"{self.base}/list/{settings.CLICKUP_LIST_ID}/task", json=body, headers=self._h()), self.label)
        return TaskRef(str(data["id"]), data.get("url"), (data.get("status") or {}).get("status"))

    async def fetch_status(self, external_id):
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            data = self.check(await c.get(f"{self.base}/task/{external_id}", headers=self._h()), self.label)
        st = data.get("status") or {}
        raw = st.get("status") or ""
        mapped = "completed" if st.get("type") in ("done", "closed") else map_status_text(raw)
        return raw, mapped


    async def check_connection(self):
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            data = self.check(await c.get(f"{self.base}/list/{settings.CLICKUP_LIST_ID}", headers=self._h()), self.label)
        return f"list \"{data.get('name', settings.CLICKUP_LIST_ID)}\""


class Jira(Provider):
    name, label = "jira", "Jira"
    required_env = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"]

    def configured(self) -> bool:
        return bool(settings.JIRA_BASE_URL and settings.JIRA_EMAIL and settings.JIRA_API_TOKEN and settings.JIRA_PROJECT_KEY)

    @property
    def base(self):
        return settings.JIRA_BASE_URL.rstrip("/")

    def _auth(self):
        return (settings.JIRA_EMAIL, settings.JIRA_API_TOKEN)

    async def create_task(self, *, title, description, due, assignee_email):
        fields: Dict = {
            "project": {"key": settings.JIRA_PROJECT_KEY},
            "summary": title[:250],
            "issuetype": {"name": settings.JIRA_ISSUE_TYPE},
            # Jira Cloud v3 takes descriptions as Atlassian Document Format.
            "description": {"type": "doc", "version": 1, "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": description or title}]}
            ]},
        }
        if due:
            fields["duedate"] = due.isoformat()
        async with httpx.AsyncClient(timeout=TIMEOUT, auth=self._auth()) as c:
            data = self.check(await c.post(f"{self.base}/rest/api/3/issue", json={"fields": fields}), self.label)
        key = data.get("key") or str(data.get("id"))
        return TaskRef(key, f"{self.base}/browse/{key}", "To Do")

    async def fetch_status(self, external_id):
        async with httpx.AsyncClient(timeout=TIMEOUT, auth=self._auth()) as c:
            data = self.check(await c.get(f"{self.base}/rest/api/3/issue/{external_id}", params={"fields": "status"}), self.label)
        status = (data.get("fields") or {}).get("status") or {}
        raw = status.get("name") or ""
        cat = (status.get("statusCategory") or {}).get("key")
        mapped = {"done": "completed", "indeterminate": "in_progress", "new": "planned"}.get(cat) or map_status_text(raw)
        return raw, mapped


    async def check_connection(self):
        async with httpx.AsyncClient(timeout=TIMEOUT, auth=self._auth()) as c:
            data = self.check(await c.get(f"{self.base}/rest/api/3/project/{settings.JIRA_PROJECT_KEY}"), self.label)
            types = [t.get("name") for t in data.get("issueTypes") or []]
        if types and settings.JIRA_ISSUE_TYPE not in types:
            raise IntegrationError(f"Project {settings.JIRA_PROJECT_KEY} has no issue type \"{settings.JIRA_ISSUE_TYPE}\". "
                                   f"Set JIRA_ISSUE_TYPE to one of: {', '.join(types)}.")
        return f"project {data.get('key')} \"{data.get('name', '')}\" as {settings.JIRA_ISSUE_TYPE}"


class Asana(Provider):
    name, label = "asana", "Asana"
    required_env = ["ASANA_ACCESS_TOKEN", "ASANA_PROJECT_GID"]
    base = "https://app.asana.com/api/1.0"

    def configured(self) -> bool:
        return bool(settings.ASANA_ACCESS_TOKEN and settings.ASANA_PROJECT_GID)

    def _h(self):
        return {"Authorization": f"Bearer {settings.ASANA_ACCESS_TOKEN}"}

    async def create_task(self, *, title, description, due, assignee_email):
        data: Dict = {"name": title, "notes": description, "projects": [settings.ASANA_PROJECT_GID]}
        if due:
            data["due_on"] = due.isoformat()
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            body = self.check(await c.post(f"{self.base}/tasks", json={"data": data}, headers=self._h()), self.label)
        task = body.get("data") or {}
        return TaskRef(str(task["gid"]), task.get("permalink_url"), "incomplete")

    async def fetch_status(self, external_id):
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            body = self.check(
                await c.get(f"{self.base}/tasks/{external_id}", params={"opt_fields": "completed,name"}, headers=self._h()),
                self.label,
            )
        done = bool((body.get("data") or {}).get("completed"))
        return ("completed" if done else "incomplete"), ("completed" if done else None)


    async def check_connection(self):
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            body = self.check(await c.get(f"{self.base}/projects/{settings.ASANA_PROJECT_GID}",
                                          params={"opt_fields": "name"}, headers=self._h()), self.label)
        return f"project \"{(body.get('data') or {}).get('name', settings.ASANA_PROJECT_GID)}\""


class Trello(Provider):
    name, label = "trello", "Trello"
    required_env = ["TRELLO_API_KEY", "TRELLO_TOKEN", "TRELLO_LIST_ID"]
    base = "https://api.trello.com/1"

    def configured(self) -> bool:
        return bool(settings.TRELLO_API_KEY and settings.TRELLO_TOKEN and settings.TRELLO_LIST_ID)

    def _auth(self):
        return {"key": settings.TRELLO_API_KEY, "token": settings.TRELLO_TOKEN}

    async def create_task(self, *, title, description, due, assignee_email):
        params = {**self._auth(), "idList": settings.TRELLO_LIST_ID, "name": title, "desc": description}
        if due:
            params["due"] = due.isoformat()
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            card = self.check(await c.post(f"{self.base}/cards", params=params), self.label)
        return TaskRef(str(card["id"]), card.get("shortUrl") or card.get("url"), "open")

    async def fetch_status(self, external_id):
        params = {**self._auth(), "fields": "closed,dueComplete,idList"}
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            card = self.check(await c.get(f"{self.base}/cards/{external_id}", params=params), self.label)
        if card.get("dueComplete") or (settings.TRELLO_DONE_LIST_ID and card.get("idList") == settings.TRELLO_DONE_LIST_ID):
            return "done", "completed"
        if card.get("closed"):
            return "archived", "dropped"
        return "open", None


    async def check_connection(self):
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            lst = self.check(await c.get(f"{self.base}/lists/{settings.TRELLO_LIST_ID}",
                                         params={**self._auth(), "fields": "name,idBoard"}), self.label)
        return f"list \"{lst.get('name', settings.TRELLO_LIST_ID)}\""


class Monday(Provider):
    name, label = "monday", "monday.com"
    required_env = ["MONDAY_API_TOKEN", "MONDAY_BOARD_ID"]
    url = "https://api.monday.com/v2"

    def configured(self) -> bool:
        return bool(settings.MONDAY_API_TOKEN and settings.MONDAY_BOARD_ID)

    async def _gql(self, query: str, variables: Dict) -> Dict:
        headers = {"Authorization": settings.MONDAY_API_TOKEN, "Content-Type": "application/json", "API-Version": "2024-10"}
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            body = self.check(await c.post(self.url, json={"query": query, "variables": variables}, headers=headers), self.label)
        if body.get("errors") or body.get("error_message"):
            raise IntegrationError(f"monday.com error: {body.get('errors') or body.get('error_message')}")
        return body.get("data") or {}

    async def create_task(self, *, title, description, due, assignee_email):
        columns: Dict = {}
        if due:
            columns["date"] = {"date": due.isoformat()}
        q = ("mutation ($board: ID!, $name: String!, $cols: JSON) "
             "{ create_item (board_id: $board, item_name: $name, column_values: $cols) { id url } }")
        data = await self._gql(q, {"board": settings.MONDAY_BOARD_ID, "name": title, "cols": json.dumps(columns)})
        item = data.get("create_item") or {}
        return TaskRef(str(item["id"]), item.get("url"), None)

    async def fetch_status(self, external_id):
        q = "query ($ids: [ID!]) { items (ids: $ids) { column_values { id text } } }"
        data = await self._gql(q, {"ids": [external_id]})
        items = data.get("items") or []
        if not items:
            raise IntegrationError("monday.com item not found.")
        raw = next((c.get("text") or "" for c in items[0]["column_values"] if c["id"] == settings.MONDAY_STATUS_COLUMN_ID), "")
        return raw, map_status_text(raw)


    async def check_connection(self):
        data = await self._gql("query ($ids: [ID!]) { boards (ids: $ids) { name } }", {"ids": [settings.MONDAY_BOARD_ID]})
        boards = data.get("boards") or []
        if not boards:
            raise IntegrationError(f"monday.com board {settings.MONDAY_BOARD_ID} not found.")
        return f"board \"{boards[0].get('name')}\""


PROVIDERS: Dict[str, Provider] = {p.name: p for p in (ClickUp(), Jira(), Asana(), Trello(), Monday())}
