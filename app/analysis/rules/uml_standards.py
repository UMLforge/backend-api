"""UML 2.5 notation and semantics: multiplicities, composition, generalization vs realization,
interface and enumeration rules, member syntax, and use-case relationships."""
import re

from ..context import RELATION_TYPES
from ..members import CAMEL_CASE, parse_attribute, parse_operation
from ..registry import CONFORMANCE, NAMING, RELATIONSHIPS, Issue, rule

MULTIPLICITY = re.compile(r"^(\*|\d+)(\.\.(\*|\d+))?$")
UPPER_SNAKE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SINGULAR_EXCEPTIONS = re.compile(r"(ss|us|is|ics|ies|news|series|status|address)$", re.IGNORECASE)
CLASSIFIERS = ("class", "abstract", "interface", "enum")


def _valid_multiplicity(m: str) -> bool:
    match = MULTIPLICITY.match(m.replace(" ", ""))
    if not match:
        return False
    lo, hi = match.group(1), match.group(3)
    if hi is None:            # "1", "5", "*"
        return True
    if lo == "*":             # "*..3" makes no sense
        return False
    return hi == "*" or int(lo) <= int(hi)


# ---- relationships -------------------------------------------------------------------------

@rule
def multiplicity_syntax(ctx):
    for e in ctx.edges:
        bad = [m for m in (e.multA, e.multB) if m and not _valid_multiplicity(m)]
        if bad:
            yield Issue("warn", "BADMULT", "Invalid multiplicity",
                        f"'{bad[0]}' on {ctx.name(e.a)} → {ctx.name(e.b)} is not a UML multiplicity.",
                        "Use forms like 1, 0..1, *, 0..*, 1..*, 2..5 (lower bound ≤ upper bound).",
                        [e.a, e.b], {CONFORMANCE: 3}, tag="UML: multiplicity")


@rule
def composition_semantics(ctx):
    comps = [e for e in ctx.edges if e.type == "composition"]
    for e in comps:
        if e.multA and e.multA.replace(" ", "") not in ("1", "0..1"):
            yield Issue("warn", "COMPMULT", "Composite end must be 1 or 0..1",
                        f"{ctx.name(e.a)} ◆ {ctx.name(e.b)} has '{e.multA}' at the whole. A part belongs to at most one whole at a time.",
                        "Set the whole-side multiplicity to 1 (or 0..1), or use aggregation/association for shared parts.",
                        [e.a, e.b], {CONFORMANCE: 4}, tag="UML: composition")
    owners: dict[str, list[str]] = {}
    for e in comps:
        owners.setdefault(e.b, []).append(e.a)
    for part, wholes in owners.items():
        exclusive = all(e.multA.replace(" ", "") == "0..1" for e in comps if e.b == part)
        if len(wholes) >= 2 and not exclusive:
            yield Issue("warn", "SHAREDPART", "Part owned by several composites",
                        f"{ctx.name(part)} is composed by {', '.join(ctx.name(w) for w in wholes)}. "
                        "A part instance can only be owned by one whole, and dies with it.",
                        "Keep one composition, or mark each whole end 0..1 if ownership is exclusive; otherwise use aggregation.",
                        [part, *wholes], {CONFORMANCE: 4}, tag="UML: composition")
    # composition cycles: A ◆ B ◆ ... ◆ A
    graph: dict[str, list[str]] = {}
    for e in comps:
        graph.setdefault(e.a, []).append(e.b)

    def reaches(start, target, seen):
        return any(n == target or (n not in seen and reaches(n, target, seen | {n})) for n in graph.get(start, []))

    reported = set()
    for e in comps:
        if reaches(e.b, e.a, {e.b}) and frozenset((e.a, e.b)) not in reported:
            reported.add(frozenset((e.a, e.b)))
            yield Issue("crit", "COMPCYCLE", "Composition cycle",
                        f"{ctx.name(e.a)} and {ctx.name(e.b)} own each other through composition, which is impossible.",
                        "Decide which one is the whole; make the reverse link an association.",
                        [e.a, e.b], {CONFORMANCE: 10}, tag="UML: composition")


@rule
def generalization_vs_realization(ctx):
    for e in ctx.edges:
        child, parent = ctx.by_id.get(e.a), ctx.by_id.get(e.b)
        if not child or not parent:
            continue
        if e.type == "inheritance" and parent.type == "interface" and child.type in ("class", "abstract"):
            yield Issue("warn", "INHIFACE", "Class inherits from an interface",
                        f"{child.name} uses generalization to {parent.name}, but classes implement interfaces.",
                        "Change the link to Realize (dashed line, hollow triangle).",
                        [child.id, parent.id], {CONFORMANCE: 4}, tag="UML: realization")
        elif e.type == "inheritance" and child.type == "interface" and parent.type in ("class", "abstract"):
            yield Issue("crit", "IFACEFROMCLASS", "Interface inherits from a class",
                        f"Interface {child.name} cannot extend class {parent.name}.",
                        "Interfaces may only generalize other interfaces. Reverse the link or turn the class into an interface.",
                        [child.id, parent.id], {CONFORMANCE: 8}, tag="UML: generalization")
        elif e.type == "realization" and parent.type != "interface":
            yield Issue("warn", "BADREALIZE", "Realization of a non-interface",
                        f"{child.name} realizes {parent.name} ({parent.type}); realization targets an interface.",
                        f"Use Inherit to extend {parent.name}, or make {parent.name} an interface.",
                        [child.id, parent.id], {CONFORMANCE: 4}, tag="UML: realization")


@rule
def duplicate_links(ctx):
    seen = {}
    for e in ctx.edges:
        key = (e.type, frozenset((e.a, e.b)))
        if key in seen:
            yield Issue("info", "DUPEDGE", "Duplicate relationship",
                        f"{ctx.name(e.a)} and {ctx.name(e.b)} are joined by two {e.type} links.",
                        "Keep one link; give it role names if the classes really relate in two different ways.",
                        [e.a, e.b], {RELATIONSHIPS: 2}, tag="UML: association")
        seen[key] = e


@rule
def unnamed_associations(ctx):
    unnamed = [e for e in ctx.edges if e.type in ("association", "directed") and not e.label.strip()]
    if len(unnamed) >= 2:
        yield Issue("info", "NOLABEL", "Associations without names",
                    f"{len(unnamed)} associations have no name, so readers must guess what they mean.",
                    "Label each association with a verb phrase, e.g. Member — borrows → Loan.",
                    sorted({i for e in unnamed[:4] for i in (e.a, e.b)}), {CONFORMANCE: 2}, tag="UML: association")


# ---- classifiers and members --------------------------------------------------------------------

@rule
def interface_contents(ctx):
    for n in ctx.of_type("interface"):
        if n.attrs:
            yield Issue("info", "IFACEATTR", "Interface with attributes",
                        f"Interface {n.name} declares state ({n.attrs[0]}…). Interfaces describe behaviour only.",
                        "Move the attributes into the implementing classes, or use an abstract class instead.",
                        [n.id], {CONFORMANCE: 2}, tag="UML: interface")


@rule
def enumeration_literals(ctx):
    for n in ctx.of_type("enum"):
        if not n.attrs:
            yield Issue("warn", "ENUMEMPTY", "Enumeration without literals", f"{n.name} lists no values.",
                        "Add one literal per line, e.g. ACTIVE, SUSPENDED.", [n.id], {CONFORMANCE: 3}, tag="UML: enumeration")
        elif any(not UPPER_SNAKE.match(a.strip()) for a in n.attrs):
            yield Issue("info", "ENUMCASE", "Enumeration literal naming",
                        f"Literals of {n.name} should be UPPER_SNAKE_CASE constants, not typed attributes.",
                        "Write literals like STANDARD, PREMIUM; move typed data into a class.",
                        [n.id], {NAMING: 1}, tag="UML: enumeration")


@rule
def visibility_markers(ctx):
    missing = []
    for n in ctx.class_nodes:
        if n.type == "enum" or not (n.attrs or n.methods):
            continue
        members = [parse_attribute(a) for a in n.attrs] + [parse_operation(m) for m in n.methods]
        if all(m is None or m.visibility is None for m in members):
            missing.append(n)
    if missing:
        yield Issue("info", "NOVIS", "No visibility markers",
                    f"{', '.join(n.name for n in missing[:5])}{'…' if len(missing) > 5 else ''} show no member visibility, "
                    "so the design does not say what is public API and what is hidden.",
                    "Prefix members with - private, + public, # protected or ~ package, e.g. '- balance: Money'.",
                    [n.id for n in missing], {CONFORMANCE: min(6, 2 * len(missing))}, tag="UML: visibility")


@rule
def member_syntax(ctx):
    for n in ctx.class_nodes:
        if n.type == "enum":
            continue
        attrs = [(a, parse_attribute(a)) for a in n.attrs]
        ops = [(o, parse_operation(o)) for o in n.methods]
        untyped = [a for a, m in attrs if m and not m.type]
        malformed_ops = [o for o, m in ops if m is None]
        bad_case = [m.name for _, m in attrs + ops if m and not CAMEL_CASE.match(m.name)]
        if untyped:
            yield Issue("info", "UNTYPED", "Attributes without types",
                        f"{n.name}: {', '.join(untyped[:3])} {'has' if len(untyped) == 1 else 'have'} no type.",
                        "Write attributes as 'name: Type', e.g. '- dueDate: Date'.", [n.id], {CONFORMANCE: 2}, tag="UML: attribute")
        if malformed_ops:
            yield Issue("info", "BADOP", "Operation not in UML form",
                        f"{n.name}: '{malformed_ops[0]}' is not written as an operation.",
                        "Write operations as 'name(params): ReturnType', e.g. '+ renew(days: int): bool'.",
                        [n.id], {CONFORMANCE: 2}, tag="UML: operation")
        if bad_case:
            yield Issue("info", "MEMBERCASE", "Member names not camelCase",
                        f"{n.name}: {', '.join(bad_case[:3])} should start lowercase with no spaces or underscores.",
                        "Rename members to camelCase, e.g. dueDate, calculateFine().", [n.id], {NAMING: 2}, tag="UML: naming")


@rule
def singular_class_names(ctx):
    for n in ctx.class_nodes:
        name = (n.name or "").strip()
        if n.type != "enum" and len(name) > 3 and name.endswith("s") and not SINGULAR_EXCEPTIONS.search(name):
            yield Issue("info", "PLURAL", "Plural class name",
                        f"{name} looks plural. A class describes one instance; multiplicity expresses 'many'.",
                        f"Rename to {name[:-1]} and use a 0..* multiplicity on the association.",
                        [n.id], {NAMING: 2}, tag="UML: naming")


# ---- use-case diagrams --------------------------------------------------------------------------

@rule
def use_case_relationships(ctx):
    for e in ctx.edges:
        a, b = ctx.by_id.get(e.a), ctx.by_id.get(e.b)
        if not a or not b or e.type not in RELATION_TYPES:
            continue
        if a.type == b.type == "usecase":
            yield Issue("warn", "UCASSOC", "Use cases joined by an association",
                        f"'{a.name}' and '{b.name}' are associated; use cases relate through «include» or «extend».",
                        "Use a Dependency labelled «include» (always happens) or «extend» (optional), or a generalization.",
                        [a.id, b.id], {CONFORMANCE: 4}, tag="UML: use case")
        elif a.type == b.type == "actor":
            yield Issue("warn", "ACTORASSOC", "Actors joined by an association",
                        f"Actors {a.name} and {b.name} are associated; actors only relate by generalization.",
                        "Remove the link, or use Inherit if one actor is a specialized kind of the other.",
                        [a.id, b.id], {CONFORMANCE: 4}, tag="UML: use case")
        elif {a.type, b.type} & {"actor"} and ({a.type, b.type} & set(CLASSIFIERS)) and e.type != "association":
            yield Issue("info", "ACTORCLASS", "Actor wired into the class model",
                        f"{a.name} and {b.name} mix an actor with a class via {e.type}.",
                        "Connect actors to use cases; represent the user in the class model as a normal class.",
                        [a.id, b.id], {CONFORMANCE: 2}, tag="UML: use case")
