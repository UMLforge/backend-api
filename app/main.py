"""UMLforge backend: the API gateway the browser talks to.

Routers:
  /api/diagrams  saved diagrams (SQLite or Postgres)
  /api/shares    published read-only links that expire (rate limited)
  /api/analyze   rule-based local analysis
  /api/samples   example diagrams
  /api/ai/*      proxy to ai-service, with offline fallbacks
  /api/admin/*   monitoring for admins (accounts from the CLI: python -m app.admin)
"""
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from . import monitoring
from .auth import AdminStore
from .db import Database, DiagramRepo, ShareRepo
from .errors import install_error_handlers
from .routers import admin, ai, analysis, diagrams, samples, shares
from .services.ai_client import AIClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# Created at import time (not in a lifespan hook) so the app also works behind WSGI adapters such as
# PythonAnywhere's, which may not run ASGI lifespan events.
database = Database(settings.db_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await app.state.ai.close()


app = FastAPI(title="UMLforge API", version="2.2.0", lifespan=lifespan)
app.state.repo = DiagramRepo(database)
app.state.shares = ShareRepo(database)
app.state.ai = AIClient(settings.ai_service_url, settings.ai_timeout_seconds, settings.ai_service_path)
app.state.admins = AdminStore(database)
install_error_handlers(app)

if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

for module in (diagrams, analysis, samples, ai, shares, admin):
    app.include_router(module.router)


@app.middleware("http")
async def record_requests(request: Request, call_next):
    """Feeds the monitoring dashboard: counts, status codes and latency per area of the API."""
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        if request.url.path != "/api/admin/metrics":  # the dashboard's own polling isn't traffic
            monitoring.record_request(request.url.path, status, (time.perf_counter() - started) * 1000)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


# Single-container hosting (Render, Hugging Face Spaces, Koyeb...): FRONTEND_DIR makes this app serve the UI too,
# so everything is one URL and no CORS is needed. Mounted last, so /api routes always win.
if settings.frontend_dir and Path(settings.frontend_dir).is_dir():
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
