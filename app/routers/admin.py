"""Monitoring API for admins (accounts come from the CLI: python -m app.admin create-user NAME)."""
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from .. import monitoring
from ..config import settings
from ..errors import AppError
from ..ratelimit import client_ip, enforce

router = APIRouter(prefix="/api/admin", tags=["admin"])

NOT_SIGNED_IN = AppError(401, "Please sign in", "Your admin session is missing or has expired.", "Sign in again.")


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def require_admin(request: Request) -> str:
    """Dependency for every admin endpoint: the signed-in admin's username, or a 401."""
    token = bearer_token(request)
    user = token and request.app.state.admins.user_for(token)
    if not user:
        raise NOT_SIGNED_IN
    return user


LOGIN_LIMIT = (5, 900)  # 5 attempts per 15 minutes per IP


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


@router.post("/login")
async def login(body: LoginIn, request: Request) -> dict:
    await enforce(request, "admin-login", LOGIN_LIMIT, "tried to sign in")
    session = request.app.state.admins.login(body.username.strip(), body.password, client_ip(request))
    if not session:
        monitoring.record_error(401, "/api/admin/login", "Failed admin sign-in", f"user={body.username!r} ip={client_ip(request)}", "warning")
        raise AppError(401, "Wrong username or password", "", "Accounts are created on the server with the admin CLI.")
    return session


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    request.app.state.admins.logout(bearer_token(request))
    return Response(status_code=204)


@router.get("/metrics")
async def metrics(request: Request, response: Response, user: str = Depends(require_admin)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    state = request.app.state
    data_dir = str(Path(state.repo.db.path).parent) if not state.repo.db.postgres else "/"

    started = time.perf_counter()
    ai = await state.ai.status()
    ai["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    try:
        storage = monitoring.storage(state.repo.db, data_dir)
        db_ok = True
    except Exception as e:  # report the database as down instead of failing the whole dashboard
        storage, db_ok = {"kind": "PostgreSQL" if state.repo.db.postgres else "SQLite", "error": str(e)}, False

    limiter = "Upstash Redis" if settings.upstash_url else "in-memory (this process)"
    # The ai-service can be up while its model is not: recent AI failures mark it "degraded".
    recent_ai = [e for e in monitoring.recent_errors() if e["path"].startswith("/api/ai") and time.time() - e["at"] < 600]
    degraded = recent_ai[0]["title"] if recent_ai and ai.get("available") else None
    return {
        "user": user,
        "at": time.time(),
        "services": {
            "api": {"ok": True},
            "database": {"ok": db_ok, "kind": storage.get("kind"), "query_ms": storage.get("query_ms")},
            "ai": {"ok": ai.get("available", False), "degraded": degraded, "failures_10m": len(recent_ai),
                   "provider": ai.get("provider"), "model": ai.get("model"),
                   "latency_ms": ai["latency_ms"], "problem": None if ai.get("available") else ai.get("details") or ai.get("title")},
            "rate_limiter": {"ok": True, "kind": limiter},
        },
        "system": monitoring.system(data_dir),
        "storage": storage,
        "traffic": monitoring.traffic(),
        "errors": monitoring.recent_errors(),
        "limits": {"publish": settings.limit_publish, "view": settings.limit_view, "ai": settings.limit_ai,
                   "share_max_hours": settings.share_max_hours},
    }
