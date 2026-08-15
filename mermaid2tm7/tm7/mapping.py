"""Layout JSON + Model -> TM7.

Implements ``docs/04-tm7-mapping-spec.md``. Semantics come from the :class:`Model`
(element types, names, flow semantics); geometry comes from the :class:`Layout`
(positions, sizes, connector points). Neither source is consulted for the other's
job.

The coordinate transform, containment cross-check, z-ordering and Guid derivation
are all specified precisely and are unit-tested independently of the exact TM7 XML
byte format (which needs Windows validation — see ``writer.py``).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import MappingError
from ..layout.model import Cluster, Layout, Node
from . import guids
from .model import Model
from .writer import Tm7Element, Tm7Flow, build_tm7, write_tm7

# Spike A8 (scale) and A1 (min/max stencil clamp) need TMT and are not runnable
# here. Defaults below are the spec's stated pre-verification values.
DEFAULT_SCALE = 1.0
DEFAULT_MARGIN = 40  # pre-scale px
EPS = 1.0

# Placeholder clamps until spike A1 measures TMT's real accepted range.
MIN_SIZE = 20
MAX_SIZE = 2000


@dataclass
class MappingResult:
    tree: object  # xml.etree.ElementTree
    warnings: list[str]


def _tx(v: float, offset: float, scale: float) -> int:
    return round((v + offset) * scale)


def _clamp(value: int, name: str, warnings: list[str]) -> int:
    if value < MIN_SIZE:
        warnings.append(f"clamped {name} up to minimum {MIN_SIZE} (was {value})")
        return MIN_SIZE
    if value > MAX_SIZE:
        warnings.append(f"clamped {name} down to maximum {MAX_SIZE} (was {value})")
        return MAX_SIZE
    return value


def _validate_structure(model: Model, layout: Layout) -> None:
    model_ids = model.element_ids()
    layout_ids = {n.id for n in layout.nodes}
    missing = model_ids - layout_ids
    extra = layout_ids - model_ids
    if missing:
        raise MappingError(
            f"model elements missing from layout geometry: {sorted(missing)}"
        )
    if extra:
        raise MappingError(
            f"layout has nodes with no model element: {sorted(extra)}"
        )
    for flow in model.flows:
        if flow.source not in model_ids:
            raise MappingError(f"flow source {flow.source!r} is not a model element")
        if flow.target not in model_ids:
            raise MappingError(f"flow target {flow.target!r} is not a model element")


def _validate_containment(
    model: Model, layout: Layout, warnings: list[str], strict: bool
) -> None:
    """Logical (Markdown) vs geometric (SVG) containment must agree (spike A6)."""
    clusters = {c.id: c for c in layout.clusters}
    for node in layout.nodes:
        el = model.element_by_id(node.id)
        if el is None:
            continue
        logical = el.parent
        geometric = node.parent
        if logical != geometric:
            raise MappingError(
                f"containment mismatch for {node.id!r}: model says boundary "
                f"{logical!r}, geometry says {geometric!r}. TMT would generate "
                f"threats for a different trust-boundary crossing than the model "
                f"describes."
            )
        if geometric and geometric in clusters:
            c = clusters[geometric]
            if not c.contains(node.x, node.y, node.width, node.height, EPS):
                over = _shortfall(node, c)
                if strict:
                    raise MappingError(
                        f"node {node.id!r} is not fully inside boundary {c.id!r} "
                        f"(short by {over:.1f}px)"
                    )
                # grow boundary to contain (preferred per spec)
                _grow_to_contain(c, node)
                warnings.append(
                    f"grew boundary {c.id!r} to fully contain {node.id!r} "
                    f"(was short by {over:.1f}px)"
                )


def _shortfall(n: Node, c: Cluster) -> float:
    return max(
        0.0,
        c.x - n.x,
        c.y - n.y,
        (n.x + n.width) - (c.x + c.width),
        (n.y + n.height) - (c.y + c.height),
    )


def _grow_to_contain(c: Cluster, n: Node) -> None:
    left = min(c.x, n.x - EPS)
    top = min(c.y, n.y - EPS)
    right = max(c.x + c.width, n.x + n.width + EPS)
    bottom = max(c.y + c.height, n.y + n.height + EPS)
    c.x, c.y = left, top
    c.width, c.height = right - left, bottom - top


def build_mapping(
    model: Model,
    layout: Layout,
    *,
    scale: float = DEFAULT_SCALE,
    margin: int = DEFAULT_MARGIN,
    strict: bool = False,
) -> MappingResult:
    warnings: list[str] = [f"{w.code}: {w.detail}" for w in layout.warnings]
    _validate_structure(model, layout)
    _validate_containment(model, layout, warnings, strict)

    ox = margin
    oy = margin

    # boundaries first, outermost (lowest depth) first, for z-order
    tm7_elements: list[Tm7Element] = []
    for cluster in sorted(layout.clusters, key=lambda c: c.depth):
        boundary = model.boundary_by_id(cluster.id)
        name = boundary.name if boundary else cluster.label or cluster.id
        tm7_elements.append(
            Tm7Element(
                guid=guids.boundary_guid(model.id, cluster.id),
                generic_type_id="GE.TB.B",
                type_id="GE.TB.B",
                name=name,
                left=_tx(cluster.x, ox, scale),
                top=_tx(cluster.y, oy, scale),
                width=_clamp(round(cluster.width * scale), f"boundary {cluster.id} width", warnings),
                height=_clamp(round(cluster.height * scale), f"boundary {cluster.id} height", warnings),
                is_boundary=True,
                properties=boundary.properties if boundary else None,
            )
        )

    for node in layout.nodes:
        el = model.element_by_id(node.id)
        if el is None:
            raise MappingError(f"no model element for layout node {node.id!r}")
        tm7_elements.append(
            Tm7Element(
                guid=guids.element_guid(model.id, node.id),
                generic_type_id=el.type.generic_type_id,
                type_id=el.type.type_id,
                name=el.name,
                left=_tx(node.x, ox, scale),
                top=_tx(node.y, oy, scale),
                width=_clamp(round(node.width * scale), f"element {node.id} width", warnings),
                height=_clamp(round(node.height * scale), f"element {node.id} height", warnings),
                properties=el.properties,
            )
        )

    # flows
    flow_ordinal: dict[tuple[str, str], int] = {}
    tm7_flows: list[Tm7Flow] = []
    for edge in layout.edges:
        key = (edge.source, edge.target)
        ordinal = flow_ordinal.get(key, 0)
        flow_ordinal[key] = ordinal + 1
        model_flow = next(
            (f for f in model.flows if f.source == edge.source and f.target == edge.target),
            None,
        )
        sp = edge.start_point or edge.points[0]
        ep = edge.end_point or edge.points[-1]
        hp = edge.handle_point or ((sp[0] + ep[0]) / 2.0, (sp[1] + ep[1]) / 2.0)
        tm7_flows.append(
            Tm7Flow(
                guid=guids.flow_guid(model.id, edge.source, edge.target, ordinal),
                name=(model_flow.name if model_flow else edge.label) or "",
                source_guid=guids.element_guid(model.id, edge.source),
                target_guid=guids.element_guid(model.id, edge.target),
                source_x=_tx(sp[0], ox, scale),
                source_y=_tx(sp[1], oy, scale),
                target_x=_tx(ep[0], ox, scale),
                target_y=_tx(ep[1], oy, scale),
                handle_x=_tx(hp[0], ox, scale),
                handle_y=_tx(hp[1], oy, scale),
                properties=model_flow.properties if model_flow else None,
            )
        )

    tree = build_tm7(
        title=model.title,
        model_guid=guids.element_guid(model.id, "__surface__"),
        elements=tm7_elements,
        flows=tm7_flows,
    )
    return MappingResult(tree=tree, warnings=warnings)


def generate_tm7(
    model: Model,
    layout: Layout,
    output_path: str,
    *,
    scale: float = DEFAULT_SCALE,
    margin: int = DEFAULT_MARGIN,
    strict: bool = False,
) -> list[str]:
    """Generate a ``.tm7`` file. Returns non-fatal warnings."""
    result = build_mapping(model, layout, scale=scale, margin=margin, strict=strict)
    write_tm7(result.tree, output_path)
    return result.warnings
