"""Published links: a read-only copy of a diagram that anyone with the link can open until it expires.
No accounts. Abuse is limited by expiry, a size cap and per-IP rate limits."""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..config import settings
from ..db import ShareRepo
from ..errors import AppError
from ..models import Diagram
from ..ratelimit import enforce

router = APIRouter(prefix="/api/shares", tags=["shares"])

EXPIRED = AppError(404, "This link has expired", "Published diagrams are removed automatically after a while.",
                   "Ask the person who shared it to publish it again.")


class ShareIn(BaseModel):
    title: str = Field(default="Untitled", max_length=120)
    diagram: Diagram
    ttl_hours: int = Field(default=24, ge=1)


def _repo(request: Request) -> ShareRepo:
    return request.app.state.shares


@router.post("", status_code=201)
async def publish(body: ShareIn, request: Request) -> dict:
    await enforce(request, "publish", settings.limit_publish, "published")
    data = body.diagram.model_dump_json()
    if len(data) > settings.share_max_bytes:
        raise AppError(413, "This diagram is too large to publish", "It has more drawing data than allowed.",
                       "Erase some large pen drawings and try again.", details=f"{len(data)} bytes > SHARE_MAX_BYTES")
    ttl_hours = min(body.ttl_hours, settings.share_max_hours)
    return _repo(request).create(body.title, data, ttl_hours * 3600)


@router.get("/{share_id}")
async def view(share_id: str, request: Request) -> dict:
    await enforce(request, "view", settings.limit_view, "opened links")
    row = _repo(request).get(share_id)
    if row is None:
        raise EXPIRED
    return {"id": row["id"], "title": row["title"], "expires_at": row["expires_at"],
            "diagram": Diagram.model_validate_json(row["data"]).model_dump()}
