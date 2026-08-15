"""Regenerate committed SVG and layout-JSON fixtures.

Run this whenever the pinned Mermaid/mermaidx version changes or a fixture ``.mmd``
is edited. It renders each ``tests/fixtures/mermaid/*.mmd`` through mermaidx, writes
the SVG under ``tests/fixtures/svg/<renderer-version>/`` and the extracted layout
JSON under ``tests/fixtures/layout/``.

A diff in the committed outputs during review is the signal that geometry changed;
review it visually before committing (``docs/06-testing-spec.md`` §2).

    python tests/regenerate_fixtures.py
"""

from __future__ import annotations

import importlib.metadata as md
from pathlib import Path

from mermaid2tm7.extract import extract_layout
from mermaid2tm7.extract.config import build_config, inject
from mermaid2tm7.extract.renderers import get_renderer
from mermaid2tm7.layout import io as layout_io
from mermaid2tm7.tm7 import parse_model

HERE = Path(__file__).resolve().parent
MMD_DIR = HERE / "fixtures" / "mermaid"
LAYOUT_DIR = HERE / "fixtures" / "layout"


def renderer_tag() -> str:
    try:
        return f"mermaidx-{md.version('mermaidx')}"
    except md.PackageNotFoundError:
        return "mermaidx-unknown"


def main() -> None:
    tag = renderer_tag()
    svg_dir = HERE / "fixtures" / "svg" / tag
    svg_dir.mkdir(parents=True, exist_ok=True)
    LAYOUT_DIR.mkdir(parents=True, exist_ok=True)
    backend = get_renderer("mermaidx")

    for mmd in sorted(MMD_DIR.glob("*.mmd")):
        source = mmd.read_text(encoding="utf-8")
        cfg = build_config()
        svg = backend.render(inject(source, cfg), cfg)
        (svg_dir / f"{mmd.stem}.svg").write_text(svg, encoding="utf-8")

        known = parse_model(source).element_ids()
        layout = extract_layout(source, renderer="mermaidx", known_ids=known)
        # zero the timestamp so goldens are stable
        layout.provenance.generated_at = "FIXED"
        layout_io.write(layout, LAYOUT_DIR / f"{mmd.stem}.json")
        print(f"{mmd.name}: {len(layout.nodes)} nodes, {len(layout.clusters)} clusters, {len(layout.edges)} edges")

    print(f"\nSVG fixtures written under {svg_dir.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
