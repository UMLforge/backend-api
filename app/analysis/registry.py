"""Rule registry: every check is a function decorated with @rule.

A rule receives the analysis Context and yields Issue objects.
Each Issue lists the score points it removes from each dimension (`penalty`).

Adding a check takes one function in any module under analysis/rules/:

    @rule
    def my_check(ctx):
        for n in ctx.class_nodes:
            if ...:
                yield Issue("warn", "MYCODE", "Title", "What is wrong", "How to fix", [n.id], {STRUCTURE: 5}, tag="SRP")
"""
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable, Literal

Severity = Literal["crit", "warn", "info"]

# Score dimensions (name -> weight in the overall quality score).
NAMING, STRUCTURE, RELATIONSHIPS, COMPLETENESS = "Naming", "Structure", "Relationships", "Completeness"
EXTENSIBILITY = "OOP design"          # SOLID, encapsulation, coupling, inheritance use
CONFORMANCE = "UML conformance"       # notation and semantics from the UML 2.5 spec
WEIGHTS = {NAMING: 0.15, STRUCTURE: 0.20, RELATIONSHIPS: 0.20, COMPLETENESS: 0.15, EXTENSIBILITY: 0.15, CONFORMANCE: 0.15}


@dataclass
class Issue:
    sev: Severity
    code: str
    title: str
    detail: str
    fix: str
    ids: list[str] = field(default_factory=list)  # node ids the UI highlights
    penalty: dict[str, float] = field(default_factory=dict)  # dimension -> points removed
    tag: str = ""  # principle or standard behind the check, e.g. "SRP", "UML: composition"

    def public(self) -> dict:
        d = asdict(self)
        d.pop("penalty")
        return d


Rule = Callable[["Context"], Iterable[Issue]]  # noqa: F821  (Context lives in context.py)
RULES: list[Rule] = []


def rule(fn: Rule) -> Rule:
    RULES.append(fn)
    return fn
