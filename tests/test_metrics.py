"""Fidelity metrics (``docs/06-testing-spec.md`` §7).

Quantitative regression guards asserted as thresholds. These operate on the
committed layout geometry, which is what gets copied into TM7.
"""

from __future__ import annotations

import pytest

from mermaid2tm7.extract import extract_layout_from_svg
from mermaid2tm7.tm7 import parse_model

from conftest import MMD_DIR, svg_dir


def _layout(name: str):
    svg_path = svg_dir() / f"{name}.svg"
    if not svg_path.exists():
        pytest.skip(f"no svg for {name}")
    source = (MMD_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    known = parse_model(source).element_ids()
    return extract_layout_from_svg(svg_path.read_text(encoding="utf-8"), source=source, known_ids=known)


def _overlap_area(a, b) -> float:
    ix = max(0.0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
    iy = max(0.0, min(a.y + a.height, b.y + b.height) - max(a.y, b.y))
    return ix * iy


def test_no_node_overlap(fixture_name):
    layout = _layout(fixture_name)
    nodes = layout.nodes
    total = 0.0
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            total += _overlap_area(nodes[i], nodes[j])
    # Mermaid's own layout does not overlap nodes; allow a tiny rounding budget.
    assert total < 1.0, f"node overlap area {total:.2f} on {fixture_name}"


def test_elements_inside_assigned_boundary(fixture_name):
    layout = _layout(fixture_name)
    clusters = {c.id: c for c in layout.clusters}
    outside = 0
    for n in layout.nodes:
        if n.parent and n.parent in clusters:
            c = clusters[n.parent]
            if not c.contains(n.x, n.y, n.width, n.height, eps=1.5):
                outside += 1
    assert outside == 0, f"{outside} elements outside their boundary on {fixture_name}"


def test_logical_matches_geometric_containment(fixture_name):
    layout = _layout(fixture_name)
    source = (MMD_DIR / f"{fixture_name}.mmd").read_text(encoding="utf-8")
    model = parse_model(source)
    mismatches = []
    for n in layout.nodes:
        el = model.element_by_id(n.id)
        if el and el.parent != n.parent:
            mismatches.append((n.id, el.parent, n.parent))
    assert not mismatches, f"containment mismatches on {fixture_name}: {mismatches}"
