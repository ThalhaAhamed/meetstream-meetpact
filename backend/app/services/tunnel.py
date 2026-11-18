"""A public address for laptop installs: a Cloudflare quick tunnel, started for you.

MeetStream has to reach this server during a call - for the stand-up host's
tools (leave the meeting, who is in the call), its MCP lookups, and the
lifecycle/participant webhooks. A laptop has no public address. When
PUBLIC_URL is not set and `cloudflared` is installed, this starts
`cloudflared tunnel --url http://127.0.0.1:<port>`, reads the
https://….trycloudflare.com address it prints, checks that /api/health answers
through it, and makes it the public URL bots and agents use. If cloudflared
exits it is restarted (the address then changes; new bots use the new one).

Only MeetStream's paths are reachable through the tunnel (see TUNNEL_PATHS and
the guard in app.main): sign-in, the UI and the rest of the API stay local.
Pattern taken from MeetStream's companion app.

A thread reads cloudflared's output: asyncio subprocesses need the Proactor
loop on Windows, which uvicorn does not always use.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Deque, Optional

import httpx

from app.config import settings

log = logging.getLogger(__name__)

#: What MeetStream needs to reach. Everything else is refused on the tunnel.
TUNNEL_PATHS = ("/mcp", "/api/webhooks/", "/api/agent/", "/api/health")

_URL_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com", re.IGNORECASE)
URL_TIMEOUT = 45  # seconds for cloudflared to print its address
REACHABLE_TIMEOUT = 60  # seconds for the new name to answer (DNS takes a moment)
MAX_RESTARTS = 5

_WINDOWS_PATHS = (
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\Program Files\cloudflared\cloudflared.exe",
)


def find_cloudflared() -> Optional[str]:
    if settings.CLOUDFLARED_PATH and Path(settings.CLOUDFLARED_PATH).is_file():
        return settings.CLOUDFLARED_PATH
    found = shutil.which("cloudflared")
    if found:
        return found
    if sys.platform == "win32":
        return next((p for p in _WINDOWS_PATHS if Path(p).is_file()), None)
    return None


class TunnelManager:
    def __init__(self) -> None:
        self.state = "off"  # off | starting | up | failed
        self.url: Optional[str] = None
        self.error: Optional[str] = None
        self._proc: Optional[subprocess.Popen] = None
        self._candidate: Optional[str] = None
        self._log: Deque[str] = deque(maxlen=30)
        self._lock = threading.Lock()
        self._restarts = 0

    def wanted(self) -> bool:
        return not settings.PUBLIC_URL and not settings.app_url_is_public and settings.TUNNEL.lower() == "auto"

    def describe(self) -> dict:
        return {"state": self.state, "url": self.url, "error": self.error}

    def _spawn(self) -> bool:
        binary = find_cloudflared()
        if not binary:
            self.state, self.error = "failed", "cloudflared is not installed (see docs/configuration.md#public-url)."
            return False
        args = [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{settings.PORT}"]
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "text": True, "bufsize": 1}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(args, **kwargs)
        except OSError as exc:
            self.state, self.error = "failed", f"cloudflared could not be started: {exc}"
            return False
        with self._lock:
            self._proc, self._candidate = proc, None
            self._log.clear()
        self.state, self.url, self.error = "starting", None, None
        threading.Thread(target=self._read, args=(proc,), name="cloudflared-output", daemon=True).start()
        log.info("Started cloudflared for http://127.0.0.1:%s", settings.PORT)
        return True

    def _read(self, proc: subprocess.Popen) -> None:
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip()
            if not line:
                continue
            with self._lock:
                self._log.append(line)
                if self._candidate is None and (m := _URL_RE.search(line)):
                    self._candidate = m.group(0).lower()

    async def _wait_until_up(self) -> bool:
        for _ in range(URL_TIMEOUT * 2):
            if self._candidate or (self._proc and self._proc.poll() is not None):
                break
            await asyncio.sleep(0.5)
        if not self._candidate:
            self.state, self.error = "failed", "cloudflared did not report an address."
            return False
        url = self._candidate
        for _ in range(REACHABLE_TIMEOUT // 2):
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    if (await client.get(f"{url}/api/health")).status_code == 200:
                        self.state, self.url = "up", url
                        log.info("Public tunnel is up: %s", url)
                        return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(2)
        self.state, self.error = "failed", "The tunnel address never answered."
        return False

    async def run(self) -> None:
        """Keep a tunnel up for as long as the server runs."""
        if not self.wanted():
            return
        while self._restarts <= MAX_RESTARTS:
            if not self._spawn():
                log.warning("Tunnel not started: %s", self.error)
                return
            if await self._wait_until_up():
                while self._proc and self._proc.poll() is None:
                    await asyncio.sleep(5)
                log.warning("cloudflared exited; restarting the tunnel")
            self.url = None
            self._restarts += 1
            await asyncio.sleep(3)
        self.state = "failed"

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self.state, self.url = "off", None


tunnel = TunnelManager()


def via_tunnel(request) -> bool:
    """Did this request arrive through our tunnel? It is marked by Cloudflare's
    headers or the tunnel's host name. (The peer address can't be used: uvicorn
    replaces it with the X-Forwarded-For value cloudflared sends.) Treating a
    local request that happens to carry these headers as tunnelled only ever
    restricts it, so this errs on the safe side."""
    if tunnel.state == "off":
        return False
    host = (request.headers.get("host") or "").split(":")[0].lower()
    tunnel_host = (tunnel.url or "").removeprefix("https://")
    return bool(request.headers.get("cf-ray") or request.headers.get("cf-connecting-ip")
                or (tunnel_host and host == tunnel_host) or host.endswith(".trycloudflare.com"))


def allowed_through_tunnel(path: str) -> bool:
    for allowed in TUNNEL_PATHS:
        base = allowed.rstrip("/")
        if path == base or path.startswith(base + "/"):
            return True
    return False
