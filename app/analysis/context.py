"""Graph facts that rules share. Each property is computed once, on first use."""
from functools import cached_property

from ..models import Diagram, Edge, Node
from .keywords import Coverage, coverage

CLASS_LIKE = {"class", "interface", "abstract", "enum"}
# Shapes that never need relationships: notes, labels and free sketch drawings.
GROUPS = {"package", "module", "component", "container", "plugin"}  # organizing frames (frontend shapes/groups.js)
ANNOTATIONS = {"note", "text", "rect", "ellipse", "diamond", "line", "arrow", "freedraw", "highlighter"} | GROUPS
RELATION_TYPES = {"association", "directed", "aggregation", "composition"}  # types that take multiplicities


def is_class_like(n: Node) -> bool:
    return n.type in CLASS_LIKE


class Context:
    def __init__(self, diagram: Diagram):
        self.problem = diagram.problem or ""
        self.nodes: list[Node] = diagram.nodes
        self.edges: list[Edge] = diagram.edges
        self.by_id: dict[str, Node] = {n.id: n for n in self.nodes}

    def name(self, node_id: str) -> str:
        n = self.by_id.get(node_id)
        return (n.name or n.type) if n else "?"

    def of_type(self, *types: str) -> list[Node]:
        return [n for n in self.nodes if n.type in types]

    @cached_property
    def class_nodes(self) -> list[Node]:
        return [n for n in self.nodes if is_class_like(n)]

    @cached_property
    def structural_nodes(self) -> list[Node]:
        return [n for n in self.nodes if n.type not in ANNOTATIONS]

    @cached_property
    def degree(self) -> dict[str, int]:
        deg = {n.id: 0 for n in self.nodes}
        for e in self.edges:
            deg[e.a] = deg.get(e.a, 0) + 1
            deg[e.b] = deg.get(e.b, 0) + 1
        return deg

    @cached_property
    def components(self) -> int:
        """Number of connected groups among structural shapes."""
        adj: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            adj.setdefault(e.a, []).append(e.b)
            adj.setdefault(e.b, []).append(e.a)
        seen: set[str] = set()
        count = 0
        for n in self.structural_nodes:
            if n.id in seen:
                continue
            count += 1
            stack = [n.id]
            seen.add(n.id)
            while stack:
                for m in adj.get(stack.pop(), []):
                    if m not in seen:
                        seen.add(m)
                        stack.append(m)
        return count

    @cached_property
    def inheritance(self) -> list[Edge]:
        return [e for e in self.edges if e.type == "inheritance"]

    @cached_property
    def parents(self) -> dict[str, list[str]]:
        """child id -> parent ids, through inheritance (generalization) edges."""
        out: dict[str, list[str]] = {}
        for e in self.inheritance:
            out.setdefault(e.a, []).append(e.b)
        return out

    @cached_property
    def children(self) -> dict[str, list[str]]:
        """parent id -> child ids, through inheritance AND realization (anything that specializes it)."""
        out: dict[str, list[str]] = {}
        for e in self.edges:
            if e.type in ("inheritance", "realization"):
                out.setdefault(e.b, []).append(e.a)
        return out

    def depth(self, node_id: str, _seen: frozenset = frozenset()) -> int:
        """Length of the longest inheritance chain above a class (0 = no parent). Cycle-safe."""
        if node_id in _seen:
            return 0
        return max((1 + self.depth(p, _seen | {node_id}) for p in self.parents.get(node_id, [])), default=0)

    def edges_of(self, node_id: str, *types: str) -> list[Edge]:
        return [e for e in self.edges if (e.a == node_id or e.b == node_id) and (not types or e.type in types)]

    @cached_property
    def coverage(self) -> Coverage:
        return coverage(self.problem, [n.name for n in self.class_nodes])
