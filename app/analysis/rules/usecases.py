from ..registry import RELATIONSHIPS, Issue, rule


@rule
def actors_and_use_cases(ctx):
    actors, use_cases = ctx.of_type("actor"), ctx.of_type("usecase")
    if actors and not use_cases:
        yield Issue("warn", "NOUC", "Actors but no use cases",
                    "There are actors yet no use-case ovals, so nobody can see what the actors actually do.",
                    "Add one oval per goal, e.g. Borrow book, Pay fine, and link actors to them.")
    if use_cases and not actors:
        yield Issue("warn", "NOACTOR", "Use cases but no actors", "Use cases exist with no actor to initiate them.",
                    "Add the primary actor, e.g. Member or Customer, outside the system boundary.")
    for a in actors:
        if ctx.degree.get(a.id, 0) == 0:
            yield Issue("warn", "LONELYACTOR", "Actor with no links", f"Actor {a.name} touches nothing.",
                        "Link it to each use case it initiates with an association.", [a.id], {RELATIONSHIPS: 5})
    for u in use_cases:
        if ctx.degree.get(u.id, 0) == 0:
            yield Issue("warn", "LONELYUC", "Use case with no actor", f"Use case {u.name} has no actor or system link.",
                        "Connect the initiating actor, and any included or extended cases.", [u.id], {RELATIONSHIPS: 5})
