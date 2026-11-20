"""Turns issues into dimension scores, overall quality, flaw score and grade."""
from .context import Context
from .registry import COMPLETENESS, WEIGHTS, Issue

GRADES = [(90, "S"), (80, "A"), (65, "B"), (50, "C"), (35, "D"), (0, "F")]


def _clamp(v: float) -> int:
    return max(0, min(100, round(v)))


def _baseline(ctx: Context) -> dict[str, float]:
    base = {dim: 100.0 for dim in WEIGHTS}
    # Completeness starts from how many problem keywords appear as classes.
    pct = ctx.coverage.pct
    if pct is None:
        base[COMPLETENESS] = 70.0 if ctx.nodes else 0.0
    else:
        base[COMPLETENESS] = pct * 0.75 + 18
    return base


def score(ctx: Context, issues: list[Issue]) -> dict:
    dims = _baseline(ctx)
    for issue in issues:
        for dim, points in issue.penalty.items():
            dims[dim] -= points
    dims = {d: _clamp(v) for d, v in dims.items()}

    overall = _clamp(sum(dims[d] * w for d, w in WEIGHTS.items())) if ctx.nodes else 0
    grade = next(g for limit, g in GRADES if overall >= limit)
    return {"overall": overall, "flaw": 100 - overall, "grade": grade, "dims": dims}
