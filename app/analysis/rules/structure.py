from ..registry import COMPLETENESS, EXTENSIBILITY, RELATIONSHIPS, STRUCTURE, Issue, rule


def _is_god(attrs: int, methods: int) -> bool:
    return attrs + methods >= 14 or attrs >= 9 or methods >= 11


@rule
def empty_canvas(ctx):
    if not ctx.nodes:
        yield Issue("crit", "EMPTY", "Empty canvas", "There are no shapes at all, so there is nothing to evaluate.",
                    "Drop a few classes from the toolbar, or press Generate starter diagram.")


@rule
def class_size(ctx):
    data_only = []
    for n in ctx.class_nodes:
        if n.type == "enum":
            continue
        na, nm = len(n.attrs), len(n.methods)
        if na == 0 and nm == 0:
            yield Issue("warn", "EMPTYCLASS", "Empty class",
                        f"{n.name} has no attributes and no methods. It may be a missing abstraction or a half-drawn idea.",
                        "Add 2 to 5 attributes and 1 to 4 methods, or merge it into a related class.",
                        [n.id], {STRUCTURE: 9, COMPLETENESS: 4})
        elif _is_god(na, nm):
            yield Issue("crit", "GOD", "God class",
                        f"{n.name} carries {na + nm} members. Large classes become hard to change and test.",
                        "Split by responsibility: move a coherent group of members into a new class linked by association.",
                        [n.id], {STRUCTURE: 14, EXTENSIBILITY: 8}, tag="SRP")
        elif nm == 0 and na >= 2:
            data_only.append(n)
    if len(data_only) >= 3:
        yield Issue("info", "ANEMIC", "Many data-only classes",
                    "Several classes hold data but no behavior. Fine for DTOs, but a fully anemic model pushes all logic elsewhere.",
                    "Move 1 or 2 key behaviors onto the data they use most, e.g. Loan.isOverdue.",
                    [n.id for n in data_only[:4]], tag="Tell, don't ask")


@rule
def disconnected_shapes(ctx):
    # Actors and use cases have their own rules (usecases.py).
    orphans = [n for n in ctx.structural_nodes
               if ctx.degree.get(n.id, 0) == 0 and n.type not in ("actor", "usecase")]
    if len(orphans) == 1 and not ctx.edges and len(ctx.structural_nodes) <= 2:
        yield Issue("info", "START", "Just getting started", "A single unconnected shape is a fine beginning, not a flaw.",
                    "Add the next domain concept and connect the two with an association, then analyze again.",
                    [orphans[0].id])
        return
    for n in orphans:
        yield Issue("warn", "ORPHAN", "Disconnected shape",
                    f"{n.name or n.type} has no relationships. Reviewers will ask how it fits.",
                    "Connect it with an association, inheritance or dependency, or delete it if it is out of scope.",
                    [n.id], {STRUCTURE: 6, COMPLETENESS: 3})


@rule
def fragmented_model(ctx):
    comps = ctx.components
    if len(ctx.structural_nodes) >= 3 and comps >= 3:
        yield Issue("warn", "FRAGMENT", "Fragmented model",
                    f"The diagram splits into {comps} disconnected groups. A coherent domain model is usually one connected story.",
                    "Add the missing associations between groups, e.g. which class creates or references which.",
                    penalty={STRUCTURE: (comps - 2) * 7})


@rule
def link_density(ctx):
    shapes = len(ctx.structural_nodes)
    if not shapes:
        return
    density = len(ctx.edges) / shapes
    if shapes >= 4 and density < 0.5:
        yield Issue("warn", "SPARSE", "Under-connected model",
                    f"Only {len(ctx.edges)} links for {shapes} shapes. Real domains are more tangled.",
                    "Look for owns, manages, creates, pays, logs or references relations you forgot.",
                    penalty={RELATIONSHIPS: 12})
    elif shapes >= 5 and density > 2.5:
        yield Issue("info", "DENSE", "Very dense model",
                    f"{len(ctx.edges)} links for {shapes} shapes can be hard to read.",
                    "Check for redundant bidirectional links; keep the strongest direction.",
                    penalty={RELATIONSHIPS: 6})
