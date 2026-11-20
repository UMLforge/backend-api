"""Offline starter diagram built from problem keywords. Used whenever AI is unavailable."""
from ..analysis.keywords import keywords, stem

DEFAULT_CLASSES = ["Customer", "Order", "Product", "Payment", "Shipment", "Admin", "Report"]
MAX_CLASSES = 7


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def keyword_spec(problem: str) -> dict:
    words = [k.example for k in keywords(problem)[:MAX_CLASSES]] or DEFAULT_CLASSES
    names: list[str] = []
    for w in words:
        name = _cap(stem(w)) if len(stem(w)) >= 3 else _cap(w)
        if name not in names:
            names.append(name)

    classes = [{"name": n, "attrs": ["- id: ID", "- name: String"], "methods": ["+ save(): void", "+ validate(): bool"]}
               for n in names]
    hub = names[0]
    edges = [{"type": "composition" if i % 3 == 0 else "association", "from": hub, "to": n,
              "label": "has" if i % 2 else "uses", "multA": "1", "multB": "0..*"}
             for i, n in enumerate(names) if i > 0]
    return {"classes": classes, "edges": edges}
