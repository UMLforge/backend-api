"""Parses UML member strings.

  attribute:  [visibility] [/]name [: Type] [= default]      e.g.  "- balance: Money = 0"
  operation:  [visibility] name(params) [: ReturnType]        e.g.  "+ withdraw(amount: Money): bool"
  visibility: + public, - private, # protected, ~ package
"""
import re
from dataclasses import dataclass

VISIBILITY = {"+": "public", "-": "private", "#": "protected", "~": "package"}
_MODIFIERS = re.compile(r"^\s*(\{static\}|\{abstract\}|static|abstract)\s+", re.IGNORECASE)
_ATTR = re.compile(r"^([+\-#~])?\s*/?\s*([A-Za-z_]\w*)\s*(?::\s*([^=]+?))?\s*(?:=.*)?$")
_OPER = re.compile(r"^([+\-#~])?\s*([A-Za-z_]\w*)\s*\((.*)\)\s*(?::\s*(.+))?$")
CAMEL_CASE = re.compile(r"^[a-z][A-Za-z0-9]*$")


@dataclass(frozen=True)
class Member:
    raw: str
    visibility: str | None   # "+", "-", "#", "~" or None
    name: str
    type: str | None         # attribute type or operation return type


def _clean(raw: str) -> str:
    return _MODIFIERS.sub("", raw.strip())


def parse_attribute(raw: str) -> Member | None:
    m = _ATTR.match(_clean(raw))
    return Member(raw, m.group(1), m.group(2), (m.group(3) or "").strip() or None) if m else None


def parse_operation(raw: str) -> Member | None:
    m = _OPER.match(_clean(raw))
    return Member(raw, m.group(1), m.group(2), (m.group(4) or "").strip() or None) if m else None


def is_accessor(name: str) -> bool:
    return bool(re.match(r"^(get|set|is|has)[A-Z]", name))
