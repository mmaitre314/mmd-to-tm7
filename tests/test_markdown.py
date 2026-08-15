from __future__ import annotations

from mermaid2tm7.tm7 import parse_model
from mermaid2tm7.tm7.markdown import direction_of, extract_mermaid_block
from mermaid2tm7.tm7.model import ElementType


def test_extract_block_from_markdown():
    md = "# Title\n\n```mermaid\nflowchart LR\n a-->b\n```\n\ntext"
    block = extract_mermaid_block(md)
    assert "flowchart LR" in block
    assert "text" not in block


def test_bare_mmd_passthrough():
    src = "flowchart LR\n a-->b\n"
    assert extract_mermaid_block(src) == src


def test_labelled_source_edge():
    src = "flowchart LR\n a[Alpha] --> b[Beta]\n"
    m = parse_model(src)
    assert {e.id for e in m.elements} == {"a", "b"}
    assert [(f.source, f.target) for f in m.flows] == [("a", "b")]
    assert m.element_by_id("a").name == "Alpha"


def test_edge_chain():
    src = "flowchart LR\n a --> b --> c\n"
    m = parse_model(src)
    assert [(f.source, f.target) for f in m.flows] == [("a", "b"), ("b", "c")]


def test_edge_label():
    src = "flowchart LR\n a -->|does thing| b\n"
    m = parse_model(src)
    assert m.flows[0].name == "does thing"


def test_shape_types():
    src = (
        "flowchart LR\n"
        " p[Proc] --> ds[(Store)]\n"
        " ds --> ext[/Actor/]\n"
        " ext --> mp[[Multi]]\n"
    )
    m = parse_model(src)
    by = {e.id: e.type for e in m.elements}
    assert by["ds"] == ElementType.DATA_STORE
    assert by["ext"] == ElementType.EXTERNAL_INTERACTOR
    assert by["mp"] == ElementType.MULTI_PROCESS
    assert by["p"] == ElementType.PROCESS


def test_subgraph_containment():
    src = (
        "flowchart LR\n"
        " a[A] --> b[B]\n"
        " subgraph zone[Zone]\n"
        "   b --> c[C]\n"
        " end\n"
    )
    m = parse_model(src)
    assert m.element_by_id("b").parent == "zone"
    assert m.element_by_id("c").parent == "zone"
    assert m.element_by_id("a").parent is None
    assert m.boundary_by_id("zone").name == "Zone"


def test_nested_subgraph_containment():
    src = (
        "flowchart TB\n"
        " subgraph outer[Outer]\n"
        "   x[X]\n"
        "   subgraph inner[Inner]\n"
        "     y[Y]\n"
        "   end\n"
        " end\n"
    )
    m = parse_model(src)
    assert m.element_by_id("x").parent == "outer"
    assert m.element_by_id("y").parent == "inner"
    assert m.boundary_by_id("inner").parent == "outer"


def test_direction():
    assert direction_of("flowchart LR\n a-->b") == "LR"
    assert direction_of("flowchart TD\n a-->b") == "TB"
    assert direction_of("graph BT\n a-->b") == "BT"
