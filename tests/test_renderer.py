"""Renderer structural tests (``docs/06-testing-spec.md`` §4).

Re-render each fixture through mermaidx and assert the SVG still has the structure
the extractor depends on (the A2 selectors) and the right node count. When this
fails, Mermaid has changed and the committed fixtures need regenerating. Marked
``renderer`` so it can be run on a schedule as well as on PRs.
"""

from __future__ import annotations

import pytest

from mermaid2tm7.extract.config import build_config, inject
from mermaid2tm7.tm7 import parse_model

from conftest import MMD_DIR

mermaidx = pytest.importorskip("mermaidx")
pytestmark = pytest.mark.renderer


def _render(name: str) -> str:
    source = (MMD_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    cfg = build_config()
    return mermaidx.render(inject(source, cfg)).svg()


def test_structure_present(fixture_name):
    svg = _render(fixture_name)
    assert 'class="nodes"' in svg
    assert "-flowchart-" in svg
    assert "edgePaths" in svg


def test_node_count_matches_model(fixture_name):
    source = (MMD_DIR / f"{fixture_name}.mmd").read_text(encoding="utf-8")
    model = parse_model(source)
    svg = _render(fixture_name)
    count = svg.count('class="node ')
    assert count == len(model.elements), f"{fixture_name}: svg {count} vs model {len(model.elements)}"


def test_clusters_present_when_expected(fixture_name):
    source = (MMD_DIR / f"{fixture_name}.mmd").read_text(encoding="utf-8")
    model = parse_model(source)
    svg = _render(fixture_name)
    if model.boundaries:
        assert 'class="cluster ' in svg
