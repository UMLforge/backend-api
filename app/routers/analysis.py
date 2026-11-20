from fastapi import APIRouter

from ..analysis import analyze
from ..models import Diagram

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/analyze")
def analyze_diagram(diagram: Diagram) -> dict:
    return analyze(diagram)
