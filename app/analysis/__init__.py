"""Local UML analyzer: runs every registered rule, then scores the result."""
from ..models import Diagram
from . import rules  # noqa: F401  (importing registers all rules)
from .context import Context
from .registry import RULES
from .scoring import score

_SEVERITY_ORDER = {"crit": 0, "warn": 1, "info": 2}


def analyze(diagram: Diagram) -> dict:
    ctx = Context(diagram)
    issues = [issue for check in RULES for issue in check(ctx)]
    issues.sort(key=lambda i: _SEVERITY_ORDER[i.sev])
    return {
        **score(ctx, issues),
        "issues": [i.public() for i in issues],
        "coverage": ctx.coverage.public(),
        "counts": {"nodes": len(ctx.nodes), "classes": len(ctx.class_nodes), "edges": len(ctx.edges)},
    }
