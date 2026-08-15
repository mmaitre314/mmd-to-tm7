from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from mermaid2tm7.errors import MappingError
from mermaid2tm7.extract import extract_layout_from_svg
from mermaid2tm7.tm7 import generate_tm7, parse_model
from mermaid2tm7.tm7.guids import element_guid
from mermaid2tm7.tm7.mapping import build_mapping
from mermaid2tm7.tm7.model import Boundary, Element, ElementType, Flow, Model
from mermaid2tm7.tm7.writer import to_string

from conftest import MMD_DIR, svg_dir


def _all_between(text: str, start: str, end: str) -> list[str]:
    out = []
    i = 0
    while True:
        a = text.find(start, i)
        if a == -1:
            break
        b = text.find(end, a)
        out.append(text[a + len(start) : b])
        i = b
    return out


def _model_and_layout(name: str):
    source = (MMD_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    model = parse_model(source, model_id=name)
    svg = (svg_dir() / f"{name}.svg").read_text(encoding="utf-8")
    if not svg:
        pytest.skip("no svg")
    layout = extract_layout_from_svg(svg, source=source, known_ids=model.element_ids())
    return model, layout


def test_generate_azure_vm(tmp_path):
    model, layout = _model_and_layout("azure_vm")
    out = tmp_path / "azure.tm7"
    warnings = generate_tm7(model, layout, str(out), scale=1.0)
    assert out.exists()
    tree = ET.parse(out)
    # well-formed and has the expected envelope
    assert tree.getroot().tag.endswith("ThreatModel")


def test_coordinate_transform_scale_and_margin():
    model = Model(
        id="m",
        elements=[Element(id="a", name="A"), Element(id="b", name="B")],
        flows=[Flow(source="a", target="b")],
    )
    # hand-built layout
    from mermaid2tm7.layout.model import (
        Canvas,
        Edge,
        Layout,
        Node,
        Provenance,
    )

    layout = Layout(
        provenance=Provenance("v", "mermaidx", "0", "sha", "t"),
        canvas=Canvas(100, 100, (0, 0), "LR"),
        nodes=[
            Node("a", "s", "A", "rect", 0, 0, 10, 10),
            Node("b", "s", "B", "rect", 50, 0, 10, 10),
        ],
        edges=[Edge("L_a_b_0", "a", "b", points=[(10, 5), (50, 5)], start_point=(10, 5), end_point=(50, 5))],
    )
    result = build_mapping(model, layout, scale=2.0, margin=40)
    xml = to_string(result.tree)
    # element 'a' left = (0 + 40) * 2 = 80
    assert "<Left>80</Left>" in xml
    # width 10 * 2 = 20
    assert "<Width>20</Width>" in xml


def test_containment_mismatch_is_fatal():
    # model says 'a' is in boundary 'z'; geometry says it's outside
    model = Model(
        id="m",
        elements=[Element(id="a", name="A", parent="z")],
        boundaries=[Boundary(id="z", name="Zone")],
    )
    from mermaid2tm7.layout.model import Canvas, Cluster, Layout, Node, Provenance

    layout = Layout(
        provenance=Provenance("v", "mermaidx", "0", "sha", "t"),
        canvas=Canvas(100, 100, (0, 0), "LR"),
        nodes=[Node("a", "s", "A", "rect", 500, 500, 10, 10, parent=None)],
        clusters=[Cluster("z", "z", "Zone", 0, 0, 50, 50, depth=0)],
    )
    with pytest.raises(MappingError, match="containment mismatch"):
        build_mapping(model, layout)


def test_structure_mismatch_missing_element():
    model = Model(id="m", elements=[Element(id="a", name="A"), Element(id="b", name="B")])
    from mermaid2tm7.layout.model import Canvas, Layout, Node, Provenance

    layout = Layout(
        provenance=Provenance("v", "mermaidx", "0", "sha", "t"),
        canvas=Canvas(10, 10, (0, 0), "LR"),
        nodes=[Node("a", "s", "A", "rect", 0, 0, 10, 10)],
    )
    with pytest.raises(MappingError, match="missing from layout"):
        build_mapping(model, layout)


def test_guids_are_deterministic():
    assert element_guid("m", "a") == element_guid("m", "a")
    assert element_guid("m", "a") != element_guid("m", "b")
    assert element_guid("m1", "a") != element_guid("m2", "a")


def test_boundaries_written_before_elements(tmp_path):
    model, layout = _model_and_layout("nested_clusters")
    result = build_mapping(model, layout)
    xml = to_string(result.tree)
    borders = xml.split("<Borders>")[1].split("</Borders>")[0]
    first_boundary = borders.find("BorderBoundary")
    first_element = borders.find('i:type="Border"')
    assert first_boundary != -1
    assert first_boundary < first_element


def test_element_sizes_copied_from_layout(tmp_path):
    model, layout = _model_and_layout("label_extremes")
    out = tmp_path / "x.tm7"
    generate_tm7(model, layout, str(out))
    xml = out.read_text()
    # the long-label node should be markedly wider than the short-label ones,
    # proving Mermaid's text-fitted size was copied rather than a stencil default
    widths = sorted(int(w) for w in _all_between(xml, "<Width>", "</Width>"))
    assert widths[-1] > 200
    assert widths[-1] > 2 * widths[0]
