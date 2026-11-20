"""Shared data shapes. The frontend uses the exact same field names."""
from pydantic import BaseModel, ConfigDict, Field


class Node(BaseModel):
    # Drawing-only fields (strokeWidth, fillStyle, points, pressures...) pass through untouched,
    # so the frontend can add visual features without backend changes.
    model_config = ConfigDict(extra="allow")

    id: str
    type: str  # class | interface | abstract | enum | actor | usecase | note | package | text | rect | ellipse | diamond
    x: float = 0
    y: float = 0
    w: float = 180
    h: float = 120
    name: str = ""
    attrs: list[str] = Field(default_factory=list)  # attributes, or literals for an enum
    methods: list[str] = Field(default_factory=list)
    text: str = ""
    color: str = "slate"
    bg: str = "white"


class Edge(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str = "association"  # association | directed | aggregation | composition | inheritance | realization | dependency
    a: str  # source node id
    b: str  # target node id
    label: str = ""
    multA: str = ""
    multB: str = ""
    color: str = "slate"


class Diagram(BaseModel):
    problem: str = ""
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class DiagramIn(BaseModel):
    title: str = Field(default="Untitled", max_length=120)
    diagram: Diagram


class DiagramMeta(BaseModel):
    id: str
    title: str
    updated_at: float


class DiagramOut(DiagramMeta):
    diagram: Diagram


class StarterRequest(BaseModel):
    problem: str = Field(default="", max_length=8000)
