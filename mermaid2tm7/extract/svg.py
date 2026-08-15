"""Mermaid SVG -> Layout JSON.

Implements ``docs/03-svg-extraction-spec.md``. The DOM selectors below were pinned
against the SVG produced by ``mermaidx`` (spike A2, recorded in
``docs/investigation.md``):

- root ``<svg id="{root}">`` carrying ``viewBox``; a ``<g class="root">`` wrapper
- nodes: ``g.node`` with ``id="{root}-flowchart-{nodeId}-{counter}"``, node group
  ``transform`` gives the **centre**; first shape child gives the size
- clusters: ``g.cluster`` with ``id="{root}-{subgraphId}"``, child ``rect`` with
  x/y/width/height in root coordinates
- edges: ``g.edgePaths > path`` with ``data-id="L_{src}_{tgt}_{counter}"`` and ``d``
- edge labels: ``g.edgeLabels > g.edgeLabel`` with a ``transform``

If a future Mermaid version moves these, extraction raises
:class:`ExtractionError` telling the user to run ``mermaid2tm7 doctor``.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
import xml.etree.ElementTree as ET

from ..errors import ExtractionError
from ..layout.model import (
    Canvas,
    Cluster,
    Edge,
    Layout,
    Node,
    Provenance,
    Warning_,
)
from . import config as _config
from . import handles as _handles
from . import paths as _paths
from .renderers import Renderer, get_renderer
from .transforms import Affine, parse_transform

_SVG_NS = "http://www.w3.org/2000/svg"

EPS = 1.0  # containment tolerance, px
_DIR_RE = re.compile(r"\b(?:flowchart|graph)\s+(LR|RL|TB|BT|TD)\b", re.IGNORECASE)


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _classes(el: ET.Element) -> set[str]:
    return set((el.get("class") or "").split())


def _num(s: str | None, default: float = 0.0) -> float:
    if s is None:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def extract_layout(
    source: str,
    *,
    renderer: str | Renderer = "mermaidx",
    config: dict | None = None,
    handle_strategy: str = _handles.DEFAULT_STRATEGY,
    strict: bool = False,
    known_ids: set[str] | None = None,
) -> Layout:
    """Render ``source`` and extract geometry into a :class:`Layout`.

    ``known_ids``, if given, is the set of Mermaid node ids from the Markdown
    model; every extracted node id is checked against it and an unmappable node
    is a hard error (a dropped node is a missing threat-model element).
    """
    backend: Renderer = renderer if not isinstance(renderer, str) else get_renderer(renderer)
    cfg = _config.build_config(config)
    injected = _config.inject(source, cfg)
    svg_text = backend.render(injected, cfg)
    return extract_layout_from_svg(
        svg_text,
        source=source,
        renderer_name=getattr(backend, "name", "mermaidx"),
        renderer_version=backend.version(),
        mermaid_version=backend.mermaid_version(),
        handle_strategy=handle_strategy,
        strict=strict,
        known_ids=known_ids,
    )


def extract_layout_from_svg(
    svg_text: str,
    *,
    source: str = "",
    renderer_name: str = "unknown",
    renderer_version: str = "unknown",
    mermaid_version: str = "unknown",
    handle_strategy: str = _handles.DEFAULT_STRATEGY,
    strict: bool = False,
    known_ids: set[str] | None = None,
) -> Layout:
    """Extract geometry from an already-rendered SVG string.

    This is the hermetic entry point used by the golden tests — it needs no
    renderer, so committed SVG fixtures drive it directly.
    """
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        raise ExtractionError(f"could not parse SVG: {exc}") from exc

    root_id = root.get("id") or ""
    warnings: list[Warning_] = []

    nodes = _extract_nodes(root, root_id, known_ids, warnings)
    clusters = _extract_clusters(root, root_id, warnings)
    edges = _extract_edges(root, root_id, handle_strategy, warnings)

    if not nodes:
        raise ExtractionError(
            "no nodes found in SVG (expected g.node under g.nodes). This usually "
            "means the Mermaid version changed its DOM. Run `mermaid2tm7 doctor`."
        )

    _derive_containment(nodes, clusters, warnings)
    ox, oy = _normalize_origin(nodes, clusters, edges)

    vb = (root.get("viewBox") or "").split()
    width = _num(vb[2]) if len(vb) == 4 else _canvas_extent(nodes, clusters)[0]
    height = _num(vb[3]) if len(vb) == 4 else _canvas_extent(nodes, clusters)[1]

    if strict and warnings:
        raise ExtractionError(
            "extraction produced warnings under --strict: "
            + "; ".join(f"{w.code}: {w.detail}" for w in warnings)
        )

    layout = Layout(
        provenance=Provenance(
            mermaid_version=mermaid_version,
            renderer=renderer_name,
            renderer_version=renderer_version,
            source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        ),
        canvas=Canvas(
            width=width,
            height=height,
            origin_offset=(ox, oy),
            direction=_direction(source),
        ),
        nodes=nodes,
        clusters=clusters,
        edges=edges,
        warnings=warnings,
    )
    return layout


def _direction(source: str) -> str:
    m = _DIR_RE.search(source)
    if not m:
        return "TB"
    d = m.group(1).upper()
    return "TB" if d == "TD" else d


def _walk_with_ctm(root: ET.Element):
    """Yield (element, ctm) for every element, composing ancestor transforms."""
    stack: list[tuple[ET.Element, Affine]] = [(root, parse_transform(root.get("transform")))]
    while stack:
        el, ctm = stack.pop()
        yield el, ctm
        for child in list(el):
            child_ctm = ctm @ parse_transform(child.get("transform"))
            stack.append((child, child_ctm))


def _first_shape(node_el: ET.Element) -> ET.Element | None:
    for el in node_el.iter():
        tag = _local(el.tag)
        if tag in ("rect", "circle", "ellipse", "polygon", "path"):
            # skip the inner label background rects
            if tag == "rect" and "label-container" not in _classes(el) and "basic" not in _classes(el):
                continue
            return el
    return None


def _shape_bbox(shape: ET.Element, node_ctm: Affine) -> tuple[float, float, float, float]:
    ctm = node_ctm @ parse_transform(shape.get("transform"))
    tag = _local(shape.tag)
    if tag == "rect":
        x, y = _num(shape.get("x")), _num(shape.get("y"))
        w, h = _num(shape.get("width")), _num(shape.get("height"))
        corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    elif tag == "circle":
        cx, cy, r = _num(shape.get("cx")), _num(shape.get("cy")), _num(shape.get("r"))
        corners = [(cx - r, cy - r), (cx + r, cy + r)]
    elif tag == "ellipse":
        cx, cy = _num(shape.get("cx")), _num(shape.get("cy"))
        rx, ry = _num(shape.get("rx")), _num(shape.get("ry"))
        corners = [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    elif tag == "polygon":
        pts = _parse_points(shape.get("points") or "")
        corners = pts
    elif tag == "path":
        try:
            corners = _paths.parse_path(shape.get("d") or "", allow_arcs=True)
        except _paths.PathParseError:
            corners = []
    else:  # pragma: no cover
        corners = []
    if not corners:
        return (0.0, 0.0, 0.0, 0.0)
    tx = [ctm.apply(px, py) for px, py in corners]
    xs = [p[0] for p in tx]
    ys = [p[1] for p in tx]
    return (min(xs), min(ys), max(xs), max(ys))


def _parse_points(s: str) -> list[tuple[float, float]]:
    nums = [float(n) for n in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", s)]
    return list(zip(nums[0::2], nums[1::2], strict=False))


_NODE_ID_RE = re.compile(r"^(?P<root>.+?)-flowchart-(?P<id>.+)-(?P<counter>\d+)$")


def _parse_node_id(svg_id: str, root_id: str, known_ids: set[str] | None) -> str:
    """Reverse-map an SVG node id to the Mermaid node id.

    Strategy per spike A7: strip the ``{root}-flowchart-`` prefix and trailing
    ``-{counter}``. When ``known_ids`` is supplied, prefer the longest known id
    that matches, since sanitized ids can themselves contain hyphens.
    """
    m = _NODE_ID_RE.match(svg_id)
    if not m:
        raise ExtractionError(
            f"node id {svg_id!r} does not match the expected "
            f"'{{root}}-flowchart-{{id}}-{{counter}}' pattern. Run `mermaid2tm7 doctor`."
        )
    candidate = m.group("id")
    if known_ids:
        if candidate in known_ids:
            return candidate
        # fall back: match by stripping using each known id
        for kid in sorted(known_ids, key=len, reverse=True):
            if svg_id.startswith(f"{root_id}-flowchart-{kid}-"):
                return kid
        raise ExtractionError(
            f"extracted node {candidate!r} (svg id {svg_id!r}) is not in the model's "
            f"known ids {sorted(known_ids)}"
        )
    return candidate


def _extract_nodes(
    root: ET.Element,
    root_id: str,
    known_ids: set[str] | None,
    warnings: list[Warning_],
) -> list[Node]:
    nodes: list[Node] = []
    for el, ctm in _walk_with_ctm(root):
        if _local(el.tag) != "g" or "node" not in _classes(el):
            continue
        svg_id = el.get("id") or ""
        if "-flowchart-" not in svg_id:
            continue
        node_id = _parse_node_id(svg_id, root_id, known_ids)
        shape_el = _first_shape(el)
        if shape_el is None:
            raise ExtractionError(f"node {svg_id!r} has no recognizable shape child")
        minx, miny, maxx, maxy = _shape_bbox(shape_el, ctm)
        w, h = maxx - minx, maxy - miny
        if w <= 0 or h <= 0:
            raise ExtractionError(f"node {node_id!r} has zero-area bounding box")
        nodes.append(
            Node(
                id=node_id,
                svg_id=svg_id,
                label=_text_of(el),
                shape=_shape_kind(shape_el),
                x=minx,
                y=miny,
                width=w,
                height=h,
            )
        )
    return nodes


def _shape_kind(shape: ET.Element) -> str:
    tag = _local(shape.tag)
    if tag == "circle":
        return "circle"
    if tag == "ellipse":
        return "cylinder"
    if tag == "polygon":
        pts = _parse_points(shape.get("points") or "")
        return "diamond" if len(pts) == 4 else "hexagon"
    if tag == "path":
        return "stadium"  # or cylinder; both use <path>. Informational only.
    if tag == "rect":
        return "rounded" if shape.get("rx") else "rect"
    return "unknown"


def _text_of(el: ET.Element) -> str:
    parts: list[str] = []
    for t in el.iter():
        if _local(t.tag) == "text":
            parts.append("".join(s for s in t.itertext()))
    return "\n".join(p for p in (s.strip() for s in parts) if p)


def _extract_clusters(
    root: ET.Element, root_id: str, warnings: list[Warning_]
) -> list[Cluster]:
    clusters: list[Cluster] = []
    for el, ctm in _walk_with_ctm(root):
        cls = _classes(el)
        if _local(el.tag) != "g" or "cluster" not in cls or "cluster-label" in cls:
            continue
        svg_id = el.get("id") or ""
        rect = next((c for c in el.iter() if _local(c.tag) == "rect"), None)
        if rect is None:
            continue
        rctm = ctm @ parse_transform(rect.get("transform"))
        x, y = rctm.apply(_num(rect.get("x")), _num(rect.get("y")))
        w, h = _num(rect.get("width")), _num(rect.get("height"))
        if w <= 0 or h <= 0:
            raise ExtractionError(f"cluster {svg_id!r} has zero-area rect")
        cid = svg_id[len(root_id) + 1 :] if svg_id.startswith(root_id + "-") else svg_id
        clusters.append(
            Cluster(
                id=cid,
                svg_id=svg_id,
                label=_cluster_label(el),
                x=x,
                y=y,
                width=w,
                height=h,
            )
        )
    return clusters


def _cluster_label(el: ET.Element) -> str:
    for child in el.iter():
        if _local(child.tag) == "g" and "cluster-label" in _classes(child):
            return _text_of(child)
    return ""


def _extract_edges(
    root: ET.Element,
    root_id: str,
    handle_strategy: str,
    warnings: list[Warning_],
) -> list[Edge]:
    edges: list[Edge] = []
    edge_labels = _extract_edge_labels(root)
    idx = 0
    for el, ctm in _walk_with_ctm(root):
        if _local(el.tag) != "path":
            continue
        data_id = el.get("data-id") or ""
        svg_id = el.get("id") or ""
        eid = data_id or (svg_id[len(root_id) + 1 :] if svg_id.startswith(root_id + "-") else svg_id)
        if not eid.startswith("L_"):
            continue
        src, tgt = _parse_edge_endpoints(eid)
        try:
            raw = _paths.parse_path(el.get("d") or "")
        except _paths.PathParseError as exc:
            raise ExtractionError(str(exc)) from exc
        pts = [ctm.apply(px, py) for px, py in raw]
        pts = _paths.rdp(pts, epsilon=1.0)
        if len(pts) < 2:
            raise ExtractionError(f"edge {eid!r} flattened to fewer than 2 points")
        handle = _handles.reduce_to_handle(pts, handle_strategy)
        label, label_pos = edge_labels[idx] if idx < len(edge_labels) else (None, None)
        edges.append(
            Edge(
                id=eid,
                source=src,
                target=tgt,
                label=label or None,
                label_pos=label_pos,
                points=pts,
                start_point=pts[0],
                end_point=pts[-1],
                handle_point=handle,
            )
        )
        idx += 1
    _separate_parallel_edges(edges, warnings)
    return edges


def _parse_edge_endpoints(eid: str) -> tuple[str, str]:
    # id form: L_{source}_{target}_{counter}
    m = re.match(r"^L_(?P<rest>.+)_(?P<counter>\d+)$", eid)
    body = m.group("rest") if m else eid[2:]
    # source/target separated by underscore; ambiguous if ids contain underscores.
    # Best-effort split on the middle underscore.
    parts = body.split("_")
    if len(parts) == 2:
        return parts[0], parts[1]
    mid = len(parts) // 2
    return "_".join(parts[:mid]), "_".join(parts[mid:])


def _extract_edge_labels(root: ET.Element) -> list[tuple[str, tuple[float, float] | None]]:
    labels: list[tuple[str, tuple[float, float] | None]] = []
    for el, ctm in _walk_with_ctm(root):
        if _local(el.tag) != "g" or "edgeLabel" not in _classes(el):
            continue
        if "edgeLabels" in _classes(el):
            continue
        text = _text_of(el)
        pos = ctm.apply(0.0, 0.0) if el.get("transform") else None
        labels.append((text, pos))
    return labels


def _separate_parallel_edges(edges: list[Edge], warnings: list[Warning_]) -> None:
    seen: dict[tuple[str, str], int] = {}
    for e in edges:
        key = tuple(sorted((e.source, e.target)))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1 and e.handle_point and e.start_point and e.end_point:
            mag = 12.0 * (seen[key] - 1)
            ox, oy = _handles.perpendicular_offset(e.start_point, e.end_point, mag)
            e.handle_point = (e.handle_point[0] + ox, e.handle_point[1] + oy)
            warnings.append(
                Warning_(
                    code="parallel_edge_offset",
                    detail=f"offset handle of parallel edge {e.id!r} by {mag:.0f}px",
                )
            )


def _derive_containment(
    nodes: list[Node], clusters: list[Cluster], warnings: list[Warning_]
) -> None:
    # cluster depth + parent (smallest strictly-containing cluster)
    for c in clusters:
        enclosing = [
            o
            for o in clusters
            if o is not c and o.contains(c.x, c.y, c.width, c.height, EPS) and o.area > c.area
        ]
        c.parent = min(enclosing, key=lambda o: o.area).id if enclosing else None
        c.depth = _depth(c, clusters)
    for n in nodes:
        enclosing = [c for c in clusters if c.contains(n.x, n.y, n.width, n.height, EPS)]
        if enclosing:
            n.parent = min(enclosing, key=lambda c: c.area).id
        else:
            n.parent = None
        # partial overlap warning
        for c in clusters:
            if c.id == n.parent:
                continue
            if _overlaps(n, c) and not c.contains(n.x, n.y, n.width, n.height, EPS):
                over = _overlap_magnitude(n, c)
                if over > EPS:
                    warnings.append(
                        Warning_(
                            code="cluster_clips_node",
                            detail=f"node {n.id!r} extends {over:.1f}px into cluster {c.id!r} without containment",
                        )
                    )


def _depth(c: Cluster, clusters: list[Cluster]) -> int:
    depth = 0
    by_id = {cl.id: cl for cl in clusters}
    cur = c
    while cur.parent and cur.parent in by_id:
        depth += 1
        cur = by_id[cur.parent]
    return depth


def _overlaps(n: Node, c: Cluster) -> bool:
    return not (
        n.x + n.width <= c.x or n.x >= c.x + c.width or n.y + n.height <= c.y or n.y >= c.y + c.height
    )


def _overlap_magnitude(n: Node, c: Cluster) -> float:
    # how far the node pokes outside the cluster, if it overlaps a border
    left = c.x - n.x
    right = (n.x + n.width) - (c.x + c.width)
    top = c.y - n.y
    bottom = (n.y + n.height) - (c.y + c.height)
    return max(0.0, left, right, top, bottom)


def _normalize_origin(
    nodes: list[Node], clusters: list[Cluster], edges: list[Edge]
) -> tuple[float, float]:
    xs = [n.x for n in nodes] + [c.x for c in clusters]
    ys = [n.y for n in nodes] + [c.y for c in clusters]
    for e in edges:
        xs += [p[0] for p in e.points]
        ys += [p[1] for p in e.points]
    if not xs:
        return (0.0, 0.0)
    ox, oy = min(xs), min(ys)
    for n in nodes:
        n.x -= ox
        n.y -= oy
    for c in clusters:
        c.x -= ox
        c.y -= oy
    for e in edges:
        e.points = [(p[0] - ox, p[1] - oy) for p in e.points]
        e.start_point = (e.start_point[0] - ox, e.start_point[1] - oy) if e.start_point else None
        e.end_point = (e.end_point[0] - ox, e.end_point[1] - oy) if e.end_point else None
        e.handle_point = (e.handle_point[0] - ox, e.handle_point[1] - oy) if e.handle_point else None
        if e.label_pos:
            e.label_pos = (e.label_pos[0] - ox, e.label_pos[1] - oy)
    return (ox, oy)


def _canvas_extent(nodes: list[Node], clusters: list[Cluster]) -> tuple[float, float]:
    maxx = max([n.x + n.width for n in nodes] + [c.x + c.width for c in clusters], default=0.0)
    maxy = max([n.y + n.height for n in nodes] + [c.y + c.height for c in clusters], default=0.0)
    return (maxx, maxy)
