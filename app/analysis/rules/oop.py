"""Object-oriented design principles: encapsulation, SOLID, coupling, inheritance use."""
import re

from ..members import is_accessor, parse_attribute, parse_operation
from ..registry import EXTENSIBILITY, NAMING, STRUCTURE, Issue, rule

VAGUE_SUFFIX = re.compile(r"(Manager|Helper|Utils?|Handler|Processor|Data|Info|Stuff|Misc)$")
NAVIGABLE = {"association", "directed", "dependency"}
SRP_METHODS = 8          # below the god-class limit, but already doing a lot
FAT_INTERFACE = 7
MAX_DEPTH = 3
HIGH_COUPLING = 6


def _concrete_classes(ctx):
    return [n for n in ctx.class_nodes if n.type in ("class", "abstract")]


@rule
def encapsulation(ctx):
    for n in _concrete_classes(ctx):
        public = [m.name for m in map(parse_attribute, n.attrs) if m and m.visibility == "+"]
        if public:
            yield Issue("warn", "PUBLICFIELD", "Public fields break encapsulation",
                        f"{n.name} exposes its state directly: {', '.join(public[:4])}.",
                        "Make the fields private (-) and expose behaviour (methods) instead of raw data.",
                        [n.id], {EXTENSIBILITY: 4}, tag="Encapsulation")


@rule
def accessor_only_classes(ctx):
    for n in _concrete_classes(ctx):
        ops = [m for m in map(parse_operation, n.methods) if m]
        if len(ops) >= 2 and all(is_accessor(m.name) for m in ops):
            yield Issue("info", "GETSET", "Only getters and setters",
                        f"Every operation of {n.name} is a getter or setter, so the logic that uses its data lives elsewhere.",
                        "Move the behaviour that works on this data into the class (tell, don't ask).",
                        [n.id], {STRUCTURE: 3}, tag="Tell, don't ask")


@rule
def single_responsibility(ctx):
    for n in ctx.class_nodes:
        if n.type == "enum":
            continue
        if VAGUE_SUFFIX.search(n.name or ""):
            yield Issue("info", "VAGUENAME", "Vague responsibility name",
                        f"Names like {n.name} hide what the class is responsible for and tend to collect unrelated code.",
                        "Name it after the one thing it does, e.g. LoanScheduler instead of LoanManager.",
                        [n.id], {NAMING: 2}, tag="SRP")
        if SRP_METHODS <= len(n.methods) < 11:  # 11+ is already reported as a god class
            yield Issue("warn", "SRP", "Possibly more than one responsibility",
                        f"{n.name} has {len(n.methods)} operations. Classes with one reason to change rarely need that many.",
                        "Group the operations by purpose and extract each group into its own class.",
                        [n.id], {EXTENSIBILITY: 5}, tag="SRP")


@rule
def coupling(ctx):
    for n in ctx.class_nodes:
        partners = {e.b if e.a == n.id else e.a for e in ctx.edges_of(n.id) if e.type not in ("inheritance", "realization")}
        if len(partners) >= HIGH_COUPLING:
            yield Issue("warn", "COUPLING", "High coupling",
                        f"{n.name} is linked to {len(partners)} other classes, so a change in any of them can break it.",
                        "Introduce an interface or a mediator/service, or move some relations to the classes that really own them.",
                        [n.id], {STRUCTURE: 5}, tag="Low coupling")


@rule
def mutual_dependency(ctx):
    seen = set()
    for e in ctx.edges:
        if e.type not in ("dependency", "directed"):
            continue
        back = any(o.a == e.b and o.b == e.a and o.type in ("dependency", "directed") for o in ctx.edges)
        pair = frozenset((e.a, e.b))
        if back and pair not in seen:
            seen.add(pair)
            yield Issue("info", "CYCLICDEP", "Two classes depend on each other",
                        f"{ctx.name(e.a)} and {ctx.name(e.b)} depend on each other, so neither can change or be reused alone.",
                        "Break the cycle: extract an interface that one side owns, or merge them if they are one concept.",
                        [e.a, e.b], {EXTENSIBILITY: 3}, tag="Acyclic dependencies")


@rule
def program_to_interface(ctx):
    """Clients should depend on the abstraction, not on one of its concrete implementations."""
    abstraction_of = {}  # concrete class id -> the abstract class / interface it specializes
    for e in ctx.edges:
        child, parent = ctx.by_id.get(e.a), ctx.by_id.get(e.b)
        if e.type in ("inheritance", "realization") and child and parent                 and child.type == "class" and parent.type in ("abstract", "interface"):
            abstraction_of.setdefault(child.id, parent.id)
    for e in ctx.edges:
        target_parent = abstraction_of.get(e.b)
        if e.type in NAVIGABLE and target_parent and e.a != target_parent and abstraction_of.get(e.a) != target_parent:
            yield Issue("info", "CONCRETEDEP", "Depends on a concrete subclass",
                        f"{ctx.name(e.a)} uses {ctx.name(e.b)} directly although {ctx.name(target_parent)} abstracts it.",
                        f"Point the link at {ctx.name(target_parent)} so other implementations can be swapped in.",
                        [e.a, e.b], {EXTENSIBILITY: 3}, tag="DIP")


@rule
def inheritance_depth(ctx):
    for n in ctx.class_nodes:
        d = ctx.depth(n.id)
        if d > MAX_DEPTH and not any(ctx.depth(c) > d for c in ctx.children.get(n.id, [])):  # report the leaf only
            yield Issue("warn", "DEEPINH", "Deep inheritance hierarchy",
                        f"{n.name} sits {d} levels deep. Deep trees are fragile: changes at the top ripple everywhere.",
                        "Flatten the hierarchy; replace some levels with composition (has-a) or strategy objects.",
                        [n.id], {EXTENSIBILITY: 6}, tag="Composition over inheritance")


@rule
def multiple_class_inheritance(ctx):
    for child_id, parents in ctx.parents.items():
        class_parents = [p for p in parents if ctx.by_id.get(p) and ctx.by_id[p].type in ("class", "abstract")]
        if len(class_parents) >= 2:
            yield Issue("warn", "MULTIINH", "Inherits from several classes",
                        f"{ctx.name(child_id)} extends {', '.join(ctx.name(p) for p in class_parents)}. "
                        "Java, C# and most modern languages allow only one base class.",
                        "Keep one base class; turn the others into interfaces it realizes, or into parts it composes.",
                        [child_id, *class_parents], {EXTENSIBILITY: 6}, tag="Single inheritance")


@rule
def interface_segregation(ctx):
    for n in ctx.of_type("interface"):
        if len(n.methods) >= FAT_INTERFACE:
            yield Issue("warn", "FATIFACE", "Fat interface",
                        f"{n.name} declares {len(n.methods)} operations; implementers are forced to support all of them.",
                        "Split it into smaller role interfaces that clients can depend on separately.",
                        [n.id], {EXTENSIBILITY: 5}, tag="ISP")


@rule
def unused_abstraction(ctx):
    for n in ctx.of_type("abstract"):
        if not ctx.children.get(n.id):
            yield Issue("warn", "LONEABSTRACT", "Abstract class is never extended",
                        f"{n.name} is abstract, but no class inherits from it, so it can never be instantiated.",
                        "Add the concrete subclasses with Inherit links, or make it a normal class.",
                        [n.id], {STRUCTURE: 4}, tag="Abstraction")
