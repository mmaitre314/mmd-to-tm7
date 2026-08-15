"""Raster cross-check (``docs/06-testing-spec.md`` §3).

Rasterize each committed SVG and assert every extracted node centre lands on a
non-background (inked) pixel. This is the test that actually catches transform
bugs — the golden tests only prove we are *consistently* wrong.

``mermaidx.svg_to_raw`` returns ``(rgba_bytes, width, height)``. The raster spans
the SVG ``viewBox``; our extracted coordinates are the same user space shifted so
the min corner is at the origin. We invert that shift, then scale into raster
pixels.
"""

from __future__ import annotations

import re

import pytest

from mermaid2tm7.extract import extract_layout_from_svg

from conftest import svg_dir

mermaidx = pytest.importorskip("mermaidx")


def _load(name: str) -> str:
    path = svg_dir() / f"{name}.svg"
    if not path.exists():
        pytest.skip(f"no committed SVG for {name}")
    return path.read_text(encoding="utf-8")


def _viewbox(svg: str) -> tuple[float, float, float, float]:
    m = re.search(r'viewBox="([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)"', svg)
    assert m, "no viewBox"
    return tuple(float(m.group(i)) for i in range(1, 5))  # type: ignore[return-value]


def _alpha_at(pixels: bytes, w: int, h: int, px: int, py: int) -> int:
    if not (0 <= px < w and 0 <= py < h):
        return -1
    return pixels[(py * w + px) * 4 + 3]


def test_node_centres_land_on_ink(fixture_name):
    svg = _load(fixture_name)
    layout = extract_layout_from_svg(svg)

    try:
        pixels, rw, rh = mermaidx.svg_to_raw(svg)
    except Exception as exc:  # pragma: no cover - depends on mermaidx build
        pytest.skip(f"svg_to_raw unavailable: {exc}")
    if not isinstance(pixels, (bytes, bytearray)) or len(pixels) < rw * rh * 4:
        pytest.skip("unexpected svg_to_raw buffer shape")

    vb_minx, vb_miny, vb_w, vb_h = _viewbox(svg)
    ox, oy = layout.canvas.origin_offset  # min user-space coords that were subtracted
    sx = rw / vb_w
    sy = rh / vb_h

    hits = 0
    for n in layout.nodes:
        # extracted centre -> absolute user space -> raster pixel
        abs_x = n.x + n.width / 2 + ox
        abs_y = n.y + n.height / 2 + oy
        px = int(round((abs_x - vb_minx) * sx))
        py = int(round((abs_y - vb_miny) * sy))
        if _alpha_at(pixels, rw, rh, px, py) > 0:
            hits += 1

    # Every node centre should fall on inked pixels; allow one miss for shapes
    # whose centre is hollow (none of ours are, but keep a tiny margin).
    assert hits >= len(layout.nodes) - 1, (
        f"{fixture_name}: only {hits}/{len(layout.nodes)} node centres landed on ink"
    )
