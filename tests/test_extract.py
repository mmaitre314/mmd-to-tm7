from __future__ import annotations

import json

import pytest

from mermaid2tm7.extract import extract_layout_from_svg
from mermaid2tm7.layout import io as layout_io
from mermaid2tm7.tm7 import parse_model

from conftest import LAYOUT_DIR, MMD_DIR, svg_dir

TOL = 0.5


def _load_svg(name: str) -> str:
    path = svg_dir() / f"{name}.svg"
    if not path.exists():
        pytest.skip(f"no committed SVG for {name} at {path}")
    return path.read_text(encoding="utf-8")


def test_extraction_matches_golden(fixture_name):
    """SVG in -> layout JSON out, compared to the committed golden (hermetic)."""
    svg = _load_svg(fixture_name)
    source = (MMD_DIR / f"{fixture_name}.mmd").read_text(encoding="utf-8")
    known = parse_model(source).element_ids()
    layout = extract_layout_from_svg(svg, source=source, known_ids=known)

    golden = json.loads((LAYOUT_DIR / f"{fixture_name}.json").read_text(encoding="utf-8"))

    got_nodes = {n.id: n for n in layout.nodes}
    assert set(got_nodes) == {n["id"] for n in golden["nodes"]}
    for gn in golden["nodes"]:
        n = got_nodes[gn["id"]]
        assert abs(n.x - gn["x"]) < TOL, gn["id"]
        assert abs(n.y - gn["y"]) < TOL, gn["id"]
        assert abs(n.width - gn["width"]) < TOL, gn["id"]
        assert abs(n.height - gn["height"]) < TOL, gn["id"]
        assert n.parent == gn["parent"], gn["id"]

    got_clusters = {c.id: c for c in layout.clusters}
    assert set(got_clusters) == {c["id"] for c in golden["clusters"]}
    for gc in golden["clusters"]:
        c = got_clusters[gc["id"]]
        assert abs(c.x - gc["x"]) < TOL
        assert abs(c.y - gc["y"]) < TOL
        assert c.depth == gc["depth"]
        assert c.parent == gc["parent"]


def test_extraction_normalizes_origin(fixture_name):
    svg = _load_svg(fixture_name)
    layout = extract_layout_from_svg(svg)
    min_x = min([n.x for n in layout.nodes] + [c.x for c in layout.clusters])
    min_y = min([n.y for n in layout.nodes] + [c.y for c in layout.clusters])
    assert min_x >= -TOL
    assert min_y >= -TOL


def test_layout_roundtrips_through_schema(fixture_name):
    svg = _load_svg(fixture_name)
    layout = extract_layout_from_svg(svg)
    text = layout_io.dumps(layout)
    back = layout_io.loads(text)
    assert len(back.nodes) == len(layout.nodes)
    assert len(back.edges) == len(layout.edges)


def test_node_count_parity(fixture_name):
    svg = _load_svg(fixture_name)
    source = (MMD_DIR / f"{fixture_name}.mmd").read_text(encoding="utf-8")
    model = parse_model(source)
    layout = extract_layout_from_svg(svg, source=source)
    assert len(layout.nodes) == len(model.elements)
