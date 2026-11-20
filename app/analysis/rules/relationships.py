from ..context import RELATION_TYPES
from ..registry import RELATIONSHIPS, Issue, rule

MAX_LISTED = 6
POINTS_EACH, POINTS_CAP = 4, 30


@rule
def missing_multiplicity(ctx):
    missing = [e for e in ctx.edges if e.type in RELATION_TYPES and not e.multA and not e.multB]
    for e in missing[:MAX_LISTED]:
        yield Issue("info", "MULT", "Missing multiplicity",
                    f"The {e.type} between {ctx.name(e.a)} and {ctx.name(e.b)} has no multiplicity at either end.",
                    "Add ends like 1 and 0..* so implementers know the cardinality.",
                    [e.a, e.b], {RELATIONSHIPS: POINTS_EACH}, tag="UML: multiplicity")
    if len(missing) > MAX_LISTED:
        rest = min(POINTS_CAP, len(missing) * POINTS_EACH) - MAX_LISTED * POINTS_EACH
        yield Issue("info", "MULTMANY", "Many links lack multiplicities",
                    f"{len(missing)} associations have no multiplicities at all.",
                    "As a habit, end every association with explicit multiplicities.",
                    penalty={RELATIONSHIPS: max(0, rest)})


@rule
def floating_notes(ctx):
    for n in ctx.of_type("note"):
        if ctx.degree.get(n.id, 0) == 0:
            yield Issue("info", "FLOATNOTE", "Floating note", "A note is not attached to anything.",
                        "Link it to the class it explains, or fold the text into the class.", [n.id])
