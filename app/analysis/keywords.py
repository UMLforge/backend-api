"""Problem-text keyword extraction and concept coverage (no AI needed)."""
import re
from dataclasses import dataclass

STOPWORDS = frozenset("""
the and for with each that this are from into per via can has have system manage manages management
use uses used using will should must all any may also more new one two when which who what how not but
over under their they then than been between both only such other there these those allows allow make
makes part able needs need including include provides based within without during after before about
across along being doing does done very much many most some several various different multiple single
every own same software application app
""".split())


@dataclass(frozen=True)
class Keyword:
    stem: str
    count: int
    example: str  # first spelling seen in the text


def stem(word: str) -> str:
    w = word.lower()
    if len(w) > 5 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 4 and w.endswith("s"):
        return w[:-1]
    return w


def keywords(text: str, limit: int = 24) -> list[Keyword]:
    words = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split()
    counts: dict[str, int] = {}
    examples: dict[str, str] = {}
    for w in words:
        if len(w) < 4 or w in STOPWORDS:
            continue
        s = stem(w)
        counts[s] = counts.get(s, 0) + 1
        examples.setdefault(s, w)
    ranked = sorted(counts, key=lambda s: -counts[s])  # stable: ties keep text order
    return [Keyword(s, counts[s], examples[s]) for s in ranked[:limit]]


def name_stems(name: str) -> list[str]:
    """'LoanItem' -> ['loan', 'item']"""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name or "").lower()
    parts = re.sub(r"[^a-z0-9\s]", " ", spaced).split()
    return [stem(p) for p in parts if len(stem(p)) > 1]


@dataclass
class Coverage:
    keywords: list[Keyword]
    matched: list[Keyword]
    missing: list[Keyword]

    @property
    def pct(self) -> int | None:
        return round(len(self.matched) / len(self.keywords) * 100) if self.keywords else None

    def public(self) -> dict:
        return {"pct": self.pct, "matched": len(self.matched), "total": len(self.keywords),
                "missing": [k.example for k in self.missing[:8]]}


def coverage(problem: str, class_names: list[str]) -> Coverage:
    kws = keywords(problem)
    present = {s for name in class_names for s in name_stems(name)}
    matched = [k for k in kws if k.stem in present]
    missing = [k for k in kws if k.stem not in present]
    return Coverage(kws, matched, missing)
