"""FastAPI entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import agent, auth_routes, boards, calendar, knowledge, mcp, meetings, org, progress, webhooks
from app.config import REPO_DIR, settings
from app.db import init_db
from app.services.tunnel import allowed_through_tunnel, tunnel, via_tunnel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


async def _integration_loop():
    from app.db import session_scope
    from app.services import integrations

    while True:
        await asyncio.sleep(settings.INTEGRATION_SYNC_MINUTES * 60)
        if not any(p["configured"] for p in integrations.status_list()):
            continue
        try:
            with session_scope() as db:
                await integrations.sync_all(db)
        except Exception:
            log.exception("integration sync failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    tasks = []
    if settings.BACKGROUND_WORKERS:
        from app.services.workers import start_workers

        tasks = start_workers() + [asyncio.create_task(_integration_loop())]
        if tunnel.wanted():
            tasks.append(asyncio.create_task(tunnel.run()))
    if not settings.MEETSTREAM_API_KEY:
        log.warning("MEETSTREAM_API_KEY is not set: bots cannot be sent (transcript import still works).")
    if not settings.ANTHROPIC_API_KEY and not settings.GEMINI_API_KEY:
        log.warning("No ANTHROPIC_API_KEY or GEMINI_API_KEY set: transcripts cannot be analysed.")
    yield
    tunnel.stop()
    for t in tasks:
        t.cancel()


app = FastAPI(title="MeetPact", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def tunnel_guard(request: Request, call_next):
    """Through the automatic tunnel only MeetStream's paths are reachable;
    sign-in, the UI and the rest of the API stay on this machine."""
    if via_tunnel(request) and not allowed_through_tunnel(request.url.path):
        return JSONResponse({"detail": "Not available through the public tunnel."}, status_code=404)
    return await call_next(request)


for r in (auth_routes.router, org.router, meetings.router, progress.router, calendar.router, knowledge.router,
          agent.router, webhooks.router, mcp.router, boards.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}


# Serve the built frontend (npm run build) from the same origin when present.
DIST = REPO_DIR / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "mcp")):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        target = DIST / path
        if path and target.is_file() and DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
