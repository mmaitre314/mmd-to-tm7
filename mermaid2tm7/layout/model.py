"""Dataclasses mirroring the layout JSON contract (``docs/02-layout-json-spec.md``).

These are the in-memory form of the geometry passed between extraction and
mapping. ``to_dict``/``from_dict`` round-trip through the JSON schema-validated
representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LAYOUT_VERSION = "1"

Point = tuple[float, float]


@dataclass
class Provenance:
    mermaid_version: str
    renderer: str
    renderer_version: str
    source_sha256: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mermaid_version": self.mermaid_version,
            "renderer": self.renderer,
            "renderer_version": self.renderer_version,
            "source_sha256": self.source_sha256,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Provenance:
        return cls(
            mermaid_version=d["mermaid_version"],
            renderer=d["renderer"],
            renderer_version=d["renderer_version"],
            source_sha256=d["source_sha256"],
            generated_at=d["generated_at"],
        )


@dataclass
class Canvas:
    width: float
    height: float
    origin_offset: Point = (0.0, 0.0)
    direction: str = "TB"

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "origin_offset": {"x": self.origin_offset[0], "y": self.origin_offset[1]},
            "direction": self.direction,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Canvas:
        off = d.get("origin_offset", {"x": 0.0, "y": 0.0})
        return cls(
            width=d["width"],
            height=d["height"],
            origin_offset=(off["x"], off["y"]),
            direction=d.get("direction", "TB"),
        )


@dataclass
class Node:
    id: str
    svg_id: str
    label: str
    shape: str
    x: float
    y: float
    width: float
    height: float
    parent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "svg_id": self.svg_id,
            "label": self.label,
            "shape": self.shape,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "parent": self.parent,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Node:
        return cls(
            id=d["id"],
            svg_id=d["svg_id"],
            label=d["label"],
            shape=d["shape"],
            x=d["x"],
            y=d["y"],
            width=d["width"],
            height=d["height"],
            parent=d.get("parent"),
        )

    @property
    def center(self) -> Point:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)


@dataclass
class Cluster:
    id: str
    svg_id: str
    label: str
    x: float
    y: float
    width: float
    height: float
    parent: str | None = None
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "svg_id": self.svg_id,
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "parent": self.parent,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Cluster:
        return cls(
            id=d["id"],
            svg_id=d["svg_id"],
            label=d["label"],
            x=d["x"],
            y=d["y"],
            width=d["width"],
            height=d["height"],
            parent=d.get("parent"),
            depth=d.get("depth", 0),
        )

    def contains(self, x: float, y: float, w: float, h: float, eps: float = 1.0) -> bool:
        return (
            x >= self.x - eps
            and y >= self.y - eps
            and x + w <= self.x + self.width + eps
            and y + h <= self.y + self.height + eps
        )

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class Edge:
    id: str
    source: str
    target: str
    points: list[Point]
    label: str | None = None
    label_pos: Point | None = None
    start_point: Point | None = None
    end_point: Point | None = None
    handle_point: Point | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "label_pos": (
                {"x": self.label_pos[0], "y": self.label_pos[1]}
                if self.label_pos
                else None
            ),
            "points": [[p[0], p[1]] for p in self.points],
            "start_point": list(self.start_point) if self.start_point else None,
            "end_point": list(self.end_point) if self.end_point else None,
            "handle_point": list(self.handle_point) if self.handle_point else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Edge:
        lp = d.get("label_pos")
        return cls(
            id=d["id"],
            source=d["source"],
            target=d["target"],
            label=d.get("label"),
            label_pos=(lp["x"], lp["y"]) if lp else None,
            points=[(p[0], p[1]) for p in d["points"]],
            start_point=tuple(d["start_point"]) if d.get("start_point") else None,
            end_point=tuple(d["end_point"]) if d.get("end_point") else None,
            handle_point=tuple(d["handle_point"]) if d.get("handle_point") else None,
        )


@dataclass
class Warning_:
    code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Warning_:
        return cls(code=d["code"], detail=d["detail"])


@dataclass
class Layout:
    provenance: Provenance
    canvas: Canvas
    nodes: list[Node] = field(default_factory=list)
    clusters: list[Cluster] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    warnings: list[Warning_] = field(default_factory=list)
    version: str = LAYOUT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "provenance": self.provenance.to_dict(),
            "canvas": self.canvas.to_dict(),
            "nodes": [n.to_dict() for n in self.nodes],
            "clusters": [c.to_dict() for c in self.clusters],
            "edges": [e.to_dict() for e in self.edges],
            "warnings": [w.to_dict() for w in self.warnings],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Layout:
        return cls(
            version=d.get("version", LAYOUT_VERSION),
            provenance=Provenance.from_dict(d["provenance"]),
            canvas=Canvas.from_dict(d["canvas"]),
            nodes=[Node.from_dict(n) for n in d.get("nodes", [])],
            clusters=[Cluster.from_dict(c) for c in d.get("clusters", [])],
            edges=[Edge.from_dict(e) for e in d.get("edges", [])],
            warnings=[Warning_.from_dict(w) for w in d.get("warnings", [])],
        )

    def node_by_id(self, node_id: str) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)
