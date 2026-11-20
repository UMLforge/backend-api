from ..context import is_class_like
from ..registry import EXTENSIBILITY, RELATIONSHIPS, STRUCTURE, Issue, rule

WIDE_HIERARCHY = 5


def _find_cycle(ctx) -> list[str]:
    parents: dict[str, list[str]] = {}
    for e in ctx.inheritance:
        parents.setdefault(e.a, []).append(e.b)
    state: dict[str, int] = {}  # 1 = on current path, 2 = done

    def visit(node: str, path: list[str]) -> list[str]:
        state[node] = 1
        path.append(node)
        for p in parents.get(node, []):
            if state.get(p) == 1:
                return path[path.index(p):] + [p]
            if p not in state and (found := visit(p, path)):
                return found
        path.pop()
        state[node] = 2
        return []

    for start in list(parents):
        if start not in state and (cycle := visit(start, [])):
            return cycle
    return []


@rule
def inheritance_cycle(ctx):
    cycle = _find_cycle(ctx)
    if cycle:
        yield Issue("crit", "CYCLE", "Inheritance cycle",
                    "Inheritance loops back on itself: " + " → ".join(ctx.name(i) for i in cycle) + ". No language allows that.",
                    "Break the loop: one of those links should be an association or dependency instead.",
                    cycle[:-1], {RELATIONSHIPS: 35, EXTENSIBILITY: 10}, tag="UML: generalization")


@rule
def hierarchy_shape(ctx):
    children: dict[str, int] = {}
    for e in ctx.inheritance:
        children[e.b] = children.get(e.b, 0) + 1
        child, parent = ctx.by_id.get(e.a), ctx.by_id.get(e.b)
        if not child or not parent:
            continue
        if not is_class_like(child) or not is_class_like(parent):
            yield Issue("warn", "BADINH", "Inheritance to a non-class",
                        f"Inheritance from {child.name} ({child.type}) to {parent.name} ({parent.type}) is not UML-correct.",
                        "Inheritance should join two classifiers. Use association for actors and use cases.",
                        [child.id, parent.id], tag="UML: generalization")
        elif not child.attrs and not child.methods:
            yield Issue("info", "NOEXT", "Subclass adds nothing",
                        f"{child.name} extends {parent.name} but adds no members. It may be premature.",
                        "Add the specialized members, or remove the subclass until needed.",
                        [child.id], {EXTENSIBILITY: 4}, tag="YAGNI")
    for parent_id, count in children.items():
        if count >= WIDE_HIERARCHY:
            yield Issue("warn", "WIDE", "Very wide hierarchy",
                        f"{ctx.name(parent_id)} has {count} direct subclasses. Wide trees are brittle.",
                        "Group children under intermediate abstractions, or prefer composition.",
                        [parent_id], {EXTENSIBILITY: 10}, tag="Composition over inheritance")


@rule
def interfaces_and_abstraction(ctx):
    realized = {e.b for e in ctx.edges if e.type == "realization"}
    for f in ctx.of_type("interface"):
        if f.id not in realized:
            yield Issue("warn", "NOIMPL", "Interface with no implementers",
                        f"Interface {f.name} is never realized by any class.",
                        "Add a realization link from each implementing class, or remove the interface.",
                        [f.id], {STRUCTURE: 4}, tag="UML: interface")
    if len(ctx.class_nodes) >= 6 and not ctx.of_type("interface", "abstract"):
        yield Issue("info", "NOABST", "No abstraction",
                    "Six or more concrete classes with zero interfaces or abstract bases often means a rigid design.",
                    "Extract one interface for the most polymorphic role, e.g. Payment or Notification.",
                    penalty={EXTENSIBILITY: 12}, tag="Abstraction")
