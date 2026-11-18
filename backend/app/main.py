"""FastAPI entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import agent, auth_routes, calendar, knowledge, mcp, meetings, org, progress, webhooks
from app.config import REPO_DIR, settings
from app.db import init_db

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
    if not settings.MEETSTREAM_API_KEY:
        log.warning("MEETSTREAM_API_KEY is not set: bots cannot be sent (transcript import still works).")
    if not settings.ANTHROPIC_API_KEY and not settings.GEMINI_API_KEY:
        log.warning("No ANTHROPIC_API_KEY or GEMINI_API_KEY set: transcripts cannot be analysed.")
    yield
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

for r in (auth_routes.router, org.router, meetings.router, progress.router, calendar.router, knowledge.router,
          agent.router, webhooks.router, mcp.router):
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
        target = DIST / path
        if path and target.is_file() and DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
