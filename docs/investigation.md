# Investigation findings

Spike results for `01-investigation.md`. Each spike is marked with its status in
this environment. **This environment has no Windows host and no Microsoft Threat
Modeling Tool (TMT)**, so every spike that requires opening a `.tm7` in TMT, or
running `tools/tm7_validate.exe`, could not be executed here and is marked
DEFERRED with the assumption the implementation currently rests on. Spikes that
only need a renderer were run and are marked DONE.

| Spike | Status | One-line result |
|---|---|---|
| A1 Width/Height honoured | **DEFERRED** (needs TMT) | Implementation assumes yes; sizes are copied and clamped to a placeholder [20, 2000] range |
| A2 SVG DOM structure | **DONE** | Selectors pinned against mermaidx 0.9.4; see below |
| A3 Coordinate normalization | **DONE** | Full affine compose + raster cross-check passing on all 11 fixtures |
| A4 Renderer parity | **PARTIAL** | Only mermaidx runnable here; mmdc backend implemented but not benchmarked |
| A5 Connector geometry | **DEFERRED** (needs TMT) | Default handle strategy `max_deviation`; not visually confirmed in TMT |
| A6 Boundary containment | **PARTIAL** | Geometric rule + epsilon implemented and enforced; TMT's threat-generation rule not observed |
| A7 Node id round-tripping | **DONE** | id form is `{svgRootId}-flowchart-{nodeId}-{counter}`; reverse map + known-id check implemented |
| A8 Scale factor | **DEFERRED** (needs TMT) | Default `scale=1.0`, `margin=40`; not tuned against TMT |
| A9 Prior art | **NOTED** | See below |

---

## A2 — SVG DOM structure (DONE, pinned to mermaidx 0.9.4)

Rendered the whole fixture corpus through `mermaidx.render(...).svg()`. Structure:

- Root: `<svg id="{root}" viewBox="minX minY W H">`, e.g. `id="gd1"`. The root id
  prefixes every element id.
- Groups under the root `<g class="root">` (no transform in observed output):
  `g.clusters`, `g.edgePaths`, `g.edgeLabels`, `g.nodes`.
- **Nodes**: `g.node` with `id="{root}-flowchart-{nodeId}-{counter}"` and
  `transform="translate(cx, cy)"` giving the **centre**. First shape child gives
  the size:
  - rect / rounded → `rect.basic.label-container` (rounded has `rx`)
  - stadium, cylinder → `path` (uses elliptical-arc `a` commands)
  - circle → `circle`
  - hexagon, diamond → `polygon` (carries its own `transform`)
- **Clusters**: `g.cluster` (label band is a separate `g.cluster-label`) with
  `id="{root}-{subgraphId}"` and a child `rect` with `x/y/width/height` in root
  coordinates.
- **Edges**: `g.edgePaths > path` with `data-id="L_{src}_{tgt}_{counter}"` (also an
  `id="{root}-L_..."`) and a `d` of `M`/`L`/`C` commands only — no arcs.
- **Edge labels**: `g.edgeLabels > g.edgeLabel`; only labelled edges carry a
  `transform`. Matched to edges by document order.

Committed SVGs live under `tests/fixtures/svg/mermaidx-0.9.4/`. If a future
mermaidx bumps the bundled Mermaid version, `tests/test_renderer.py` fails first
and `tests/regenerate_fixtures.py` regenerates the goldens for review.

## A3 — Coordinate normalization (DONE)

`extract/transforms.py` parses the full transform grammar into 2×3 affine
matrices and composes the ancestor chain; `extract/svg.py` applies it to node
centres, cluster rects and every edge point, then shifts the min corner to the
origin and records the offset in `canvas.origin_offset`. The **raster cross-check**
(`tests/test_raster_crosscheck.py`) rasterizes each SVG via `mermaidx.svg_to_raw`
and asserts every extracted node centre lands on an inked pixel — passing on all
fixtures, which is the real guard against a transform bug.

## A4 — Renderer parity (PARTIAL)

Only `mermaidx` is installable here (no Node/Chromium reachable for a browser
benchmark), so the per-node deviation table against `mmdc` and a real browser was
not produced. The `MmdcRenderer` backend is implemented and selectable via
`--renderer mmdc`; the renderer and version are recorded in `provenance`. Default
remains `mermaidx`. **Open item**: run the deviation benchmark on a machine with
Node before promising "no fixup needed" against a VS Code preview.

## A6 — Boundary containment (PARTIAL)

Implemented and enforced: geometric parent = smallest cluster strictly containing
the box within `EPS=1.0px`; partial overlaps raise a `cluster_clips_node` warning;
the mapper **errors** on a logical-vs-geometric containment mismatch and grows a
boundary (with a warning) when a node clips its own boundary by < EPS. What could
not be observed here is *TMT's* rule for which boundary an element belongs to when
it straddles an edge, and whether that changes generated threats — that needs TMT.

## A7 — Node id round-tripping (DONE)

Ids sanitize to `{root}-flowchart-{nodeId}-{counter}`. The counter is a
per-diagram render-order index. Reverse map: strip prefix and trailing
`-{counter}`; when the model's known id set is supplied, prefer an exact/longest
known-id match so hyphenated ids survive. Unmappable ids are a hard
`ExtractionError`. Per the spec, the safest policy is to constrain generated ids
to `[A-Za-z][A-Za-z0-9_]*` upstream; the extractor never matches by label text.

## A9 — Prior art (NOTED)

Not re-surveyed in depth here. The spec's leads stand: `Part-IO/TMT2Cairis`
(TM7 → diagrams.net) for coordinate handling, `matthiasrohr/OTMT` for sample TM7
files, and any TM7 writer that already handles the `DataContractSerializer`
quirks. **The most important reuse target is the existing `tm7_cli.py` generator's
own TM7 writer** — this package's `tm7/writer.py` is a self-contained best-effort
emitter and should be reconciled with, or replaced by, that writer during
integration (see below).

---

## Load-bearing items still needing a Windows/TMT pass

These block the fidelity promise and must be closed before shipping to users:

1. **A1** — confirm TMT honours arbitrary `Width`/`Height` per stencil and find
   the real min/max clamp (placeholder `[20, 2000]` in `tm7/mapping.py`).
2. **Output verification** — every generated `.tm7` must pass
   `tools/tm7_validate.exe`. The exact `i:type` discriminators and property schema
   in `tm7/writer.py` are modelled on the documented format but have **not** been
   round-tripped through TMT here.
3. **A5** — confirm the handle strategy renders sanely, including self-loops and
   parallel edges.
4. **A8** — tune `scale`/`margin` and Mermaid `nodeSpacing`/`rankSpacing` against a
   side-by-side TMT vs preview comparison.
5. **Guid scheme** — reconcile with the skill's existing generator and
   `update-threats` round-tripping before changing anyone's Guids.
