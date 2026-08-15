"""The semantic model consumed by the TM7 mapper.

Per ``docs/04-tm7-mapping-spec.md``: *semantics come from the Markdown; geometry
comes from the SVG*. In the full skill this model is produced by the existing
``tm7_cli.py`` parser. This package defines a small, self-contained equivalent so
``mermaid2tm7`` is usable and testable on its own (``docs/05-package-and-cli-spec.md``
§Why a separate package).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ElementType(str, Enum):
    """TMT stencil families this tool can emit.

    The ``generic`` / ``type`` ids are TMT's ``GenericTypeId`` / ``TypeId`` values.
    """

    PROCESS = "process"
    MULTI_PROCESS = "multi_process"
    EXTERNAL_INTERACTOR = "external_interactor"
    DATA_STORE = "data_store"

    @property
    def generic_type_id(self) -> str:
        return {
            ElementType.PROCESS: "GE.P",
            ElementType.MULTI_PROCESS: "GE.MP",
            ElementType.EXTERNAL_INTERACTOR: "GE.EI",
            ElementType.DATA_STORE: "GE.DS",
        }[self]

    @property
    def type_id(self) -> str:
        # Generic stencils reuse the generic id as the concrete TypeId.
        return self.generic_type_id


@dataclass
class Element:
    id: str
    name: str
    type: ElementType = ElementType.PROCESS
    parent: str | None = None  # boundary id
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class Flow:
    source: str
    target: str
    name: str = ""
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class Boundary:
    id: str
    name: str
    parent: str | None = None
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class Model:
    """A whole threat model: elements, data flows and trust boundaries."""

    id: str  # stable model id, used for deterministic Guids
    title: str = "Threat Model"
    elements: list[Element] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)
    boundaries: list[Boundary] = field(default_factory=list)

    def element_ids(self) -> set[str]:
        return {e.id for e in self.elements}

    def element_by_id(self, eid: str) -> Element | None:
        return next((e for e in self.elements if e.id == eid), None)

    def boundary_by_id(self, bid: str) -> Boundary | None:
        return next((b for b in self.boundaries if b.id == bid), None)
