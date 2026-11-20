"""AI endpoints. The backend forwards these calls to ai-service and falls back to local logic when it fails."""
import logging

from fastapi import APIRouter, Request

from ..analysis import analyze
from ..analysis.context import CLASS_LIKE
from ..errors import AppError, public_details
from ..config import settings
from ..models import Diagram, StarterRequest
from ..monitoring import record_error
from ..ratelimit import enforce, enforce_global
from ..services.ai_client import AIClient, AIUnavailable
from ..services.starter_fallback import keyword_spec

log = logging.getLogger("umlforge.ai")
router = APIRouter(prefix="/api/ai", tags=["ai"])
MIN_PROBLEM_FOR_AI = 20

# Only what the model needs: no coordinates, colors or brush strokes.
AI_NODE_TYPES = CLASS_LIKE | {"actor", "usecase", "note", "package", "module", "component", "container", "plugin"}
NODE_FIELDS = {"id", "type", "name", "attrs", "methods", "text"}
EDGE_FIELDS = {"type", "a", "b", "label", "multA", "multB"}


def _ai(request: Request) -> AIClient:
    return request.app.state.ai


@router.get("/status")
async def ai_status(request: Request) -> dict:
    status = await _ai(request).status()
    return {**status, "details": public_details(status.get("details", ""))}


@router.post("/starter")
async def starter(body: StarterRequest, request: Request) -> dict:
    """Returns {"source": "ai" | "fallback", "spec": {...}, "reason"?: {title, message, hint}}."""
    await enforce(request, "ai", settings.limit_ai, "used the AI")
    await enforce_global("ai", settings.limit_ai_global, "Today's AI budget is used up",
                         "This demo allows a limited number of AI requests per day.")
    if len(body.problem.strip()) < MIN_PROBLEM_FOR_AI:
        reason = {"title": "Problem description is too short",
                  "message": "Write a sentence or two about the system so the AI can suggest classes.",
                  "hint": "",
                  "details": f"problem text under {MIN_PROBLEM_FOR_AI} characters; AI not called"}
        return {"source": "fallback", "spec": keyword_spec(body.problem), "reason": reason}
    try:
        return {"source": "ai", "spec": await _ai(request).starter(body.problem)}
    except AIUnavailable as e:
        log.warning("AI starter failed, using keyword fallback: %s | %s", e.title, e.details)
        record_error(200, "/api/ai/starter", f"Starter fell back to keywords: {e.title}", e.details, "warning")
        return {"source": "fallback", "spec": keyword_spec(body.problem), "reason": {**e.public(), "details": public_details(e.details)}}


@router.post("/review")
async def review(diagram: Diagram, request: Request) -> dict:
    """Short structured review: {grade, score, verdict, fixes[], missing[], strengths[]}."""
    await enforce(request, "ai", settings.limit_ai, "used the AI")
    await enforce_global("ai", settings.limit_ai_global, "Today's AI budget is used up",
                         "This demo allows a limited number of AI requests per day.")
    nodes = [n.model_dump(include=NODE_FIELDS) for n in diagram.nodes if n.type in AI_NODE_TYPES]
    if not any(n["type"] in CLASS_LIKE | {"actor", "usecase"} for n in nodes):
        raise AppError(400, "Nothing to review yet", "The diagram has no classes, actors or use cases.",
                       "Draw a few classes or press Generate starter diagram first.")
    kept = {n["id"] for n in nodes}
    local = analyze(diagram)
    payload = {
        "problem": diagram.problem,
        "nodes": nodes,
        "edges": [e.model_dump(include=EDGE_FIELDS) for e in diagram.edges if e.a in kept and e.b in kept],
        "local": {"overall": local["overall"], "flaw": local["flaw"], "grade": local["grade"],
                  "top_issues": [i["title"] for i in local["issues"][:5]]},
    }
    try:
        return await _ai(request).review(payload)
    except AIUnavailable as e:
        raise AppError(502, e.title, e.message, e.hint, e.details) from e
