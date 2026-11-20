import re
from collections import defaultdict

from ..registry import NAMING, Issue, rule

PLACEHOLDER = re.compile(r"^(class|iface|base|status)\d+$|^node", re.IGNORECASE)
PASCAL_CASE = re.compile(r"^[A-Z][A-Za-z0-9]*$")


@rule
def placeholder_names(ctx):
    for n in ctx.class_nodes:
        name = n.name.strip()
        if not name or PLACEHOLDER.search(name):
            yield Issue("warn", "UNNAMED", "Placeholder class name",
                        f"A class is still called {name or 'unnamed'}. Generic names carry no domain meaning.",
                        "Rename it to a domain noun from the problem, e.g. Loan, Copy, Member.",
                        [n.id], {NAMING: 9})


@rule
def duplicate_names(ctx):
    groups = defaultdict(list)
    for n in ctx.class_nodes:
        if n.name.strip():
            groups[n.name.strip().lower()].append(n)
    for same in groups.values():
        if len(same) > 1:
            yield Issue("warn", "DUPE", "Duplicate class name",
                        f"{len(same)} classes share the name {same[0].name}. That usually means one concept was drawn twice.",
                        "Merge them into one class and move the members and links across.",
                        [n.id for n in same], {NAMING: 7})


@rule
def naming_convention(ctx):
    for n in ctx.class_nodes:
        name = n.name.strip()
        if len(name) == 1:
            yield Issue("info", "ONELETTER", "Single-letter name",
                        "A one-letter class name is almost never meaningful.",
                        "Give it a domain name.", [n.id], {NAMING: 4})
        elif name and n.type != "enum" and not PASCAL_CASE.match(name):
            yield Issue("info", "CASE", "Non-standard class name",
                        f"By convention class names are PascalCase with no spaces or underscores. {name} breaks that.",
                        "Rename to PascalCase, e.g. LoanItem instead of loan_item.", [n.id], {NAMING: 3}, tag="UML: naming")
