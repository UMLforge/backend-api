from ..registry import Issue, rule

MIN_PROBLEM_CHARS = 30


@rule
def concept_coverage(ctx):
    """Completeness score is based on coverage directly (scoring.py); this rule only explains it."""
    if len(ctx.problem.strip()) < MIN_PROBLEM_CHARS:
        yield Issue("info", "NOPROB", "No problem statement",
                    "The problem box is nearly empty, so coverage cannot be judged.",
                    "Paste the assignment text into Problem so scoring can check for missing concepts.")
        return
    cov = ctx.coverage
    if cov.pct is None or not ctx.class_nodes:
        return
    missing = ", ".join(k.example for k in cov.missing[:8])
    if cov.pct < 45:
        yield Issue("warn", "COVERAGE", "Low concept coverage",
                    f"Only {len(cov.matched)} of {len(cov.keywords)} problem keywords appear as classes ({cov.pct}%). Missing: {missing}.",
                    "Add a class per missing noun, or rename a vague class to the domain word.")
    elif cov.pct < 70:
        yield Issue("info", "COVERAGE2", "Partial concept coverage",
                    f"Coverage is {cov.pct}%. Possibly missing: {missing}.",
                    "Scan the problem nouns once more and promote each important one to a class.")
