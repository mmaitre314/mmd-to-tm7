# Investigation Spikes

Run these **before** writing production code. Each spike states a question, a method, an
artifact to produce, and what to do if the answer is unfavourable. Record findings in
`docs/mermaid2tm7-investigation.md` in the repo.

Spikes are ordered by how much they can invalidate. Stop and report if a **BLOCKING** spike fails.

---

## A1 — BLOCKING — Can TM7 elements carry arbitrary Width/Height?

**Assumption.** A TM7 element node carries `Left`, `Top`, `Width`, `Height` (namespace
`http://schemas.datacontract.org/2004/07/ThreatModeling.Model.Abstracts`), and TMT honours
non-default `Width`/`Height` when rendering a stencil.

**Why it matters.** The entire fidelity approach depends on TM7 elements adopting Mermaid's
text-fitted node sizes. If sizes are pinned to stencil defaults, Mermaid coordinates will
produce overlaps and the approach collapses back to needing a layout engine with fixed node
sizes (i.e. the ELK option in `00-overview.md`).

**Method.**

1. Open a sample model in TMT, resize several stencils by hand to visibly different sizes, save,
   and diff the XML. Confirm which fields change.
2. Take an existing generated `.tm7`, hand-edit `Width`/`Height` on a few elements to extreme
   values (e.g. 40×40 and 300×120), reopen in TMT, screenshot.
3. Repeat per stencil kind: process, multi-process, external interactor, data store,
   trust boundary (border), trust line boundary, annotation.
4. Determine minimum and maximum sizes TMT will accept or silently clamp.

**Artifact.** A table: stencil type → fields present → honoured? → min/max clamp → screenshot.

**If false.** Report immediately. Fall back position is ELK with fixed TMT stencil dimensions,
accepting that TM7 will not match the Mermaid preview.

---

## A2 — BLOCKING — Exact Mermaid SVG DOM structure for flowcharts

**Assumption (to be confirmed and pinned down precisely).** For `flowchart` / `graph` diagrams
rendered by Mermaid v11:

- Nodes: `g.nodes > g.node` with `id="flowchart-<sanitizedNodeId>-<counter>"` and
  `transform="translate(x, y)"` giving the node **centre**; inner shape (`rect`, `path`,
  `polygon`, `circle`) sized around the origin
- Clusters (subgraphs): `g.clusters > g.cluster` with `id="<subgraphId>"` and a child `rect`
  carrying `x`, `y`, `width`, `height` — possibly with its own `transform`
- Edges: `g.edgePaths > path` with `id="L_<source>_<target>_<counter>"` and a `d` attribute
- Edge labels: `g.edgeLabels > g.edgeLabel` with a `transform`
- A single root `<g>` wrapper with a `transform`, plus `viewBox` on the `<svg>`

**Why it matters.** This is a rendering target, not a public API. Class names, the use of
`foreignObject` vs `<text>`, and cluster transform conventions have moved between v11 minors.

**Method.**

1. Render the repo's `samples/azure-vm.md` diagram plus purpose-built fixtures (see below) and
   dump the SVG.
2. Do this for **at least three Mermaid versions**: the version bundled in `mermaidx`, the
   version in current `@mermaid-js/mermaid-cli`, and the version used by the VS Code extension
   `bierner.markdown-mermaid`.
3. For each, record: exact selectors, whether node `transform` is centre-based, whether cluster
   rects are in root coordinates or parent-relative, and the id sanitization rules.

**Fixtures to render** (keep these as permanent test inputs):

- flat graph, 3 nodes, no subgraphs
- single subgraph containing 2 nodes, 1 edge in and 1 edge out
- **nested** subgraphs, two levels deep
- nodes with very short (`A`) and very long (60+ char) labels
- all node shapes the skill emits (rect, rounded, stadium, circle, cylinder, hexagon)
- edge with a label, bidirectional edge, self-loop, two parallel edges between the same pair
- an edge crossing a subgraph border, and an edge between two different subgraphs
- `flowchart LR` and `flowchart TB` variants of the same graph

**Artifact.** A version-comparison table and the fixture SVGs committed under
`tests/fixtures/svg/<mermaid-version>/`.

**If the structure differs materially across versions.** Pin one version in the package and
document it as a hard requirement (see A4).

---

## A3 — Coordinate space normalization

**Question.** What transform chain must be composed to get every node, cluster and edge point
into one flat, top-left-origin coordinate space?

**Method.** For each fixture, compute node centres by composing all ancestor `transform`
attributes plus the `viewBox` origin, then verify against an independent measurement: rasterize
the SVG to PNG and check that the computed centre lands inside the drawn shape. Automate this as
a test — it is the cheapest guard against a subtle transform bug.

**Watch for.**

- `viewBox` with a non-zero or negative origin
- Nested `transform` on cluster groups (children may or may not be relative to the cluster)
- `translate(x,y)` vs `translate(x, y)` vs `matrix(...)` — write a real parser, not a regex, or
  use one from an existing library
- Whether ELK-rendered output (if ever enabled) nests differently from dagre-rendered output

**Artifact.** A `normalize_transforms()` implementation plus the rasterization cross-check test.

---

## A4 — Renderer parity: what the user previews vs what we convert

**Question.** How far apart are node dimensions between renderers, and does that gap break the
"no fixup needed" promise?

**Why it matters.** Users will preview in VS Code (real browser, system fonts, typically
Trebuchet MS). `mermaidx` runs the real Mermaid library inside QuickJS-ng against a fake DOM and
bridges text metrics from a bundled DejaVu Sans. Same layout algorithm, different measurements →
different node widths → different positions. What the user approved is not quite what we
convert.

**Method.**

1. Render every fixture through: `mermaidx`, `@mermaid-js/mermaid-cli` (`mmdc`, headless
   Chrome), and a real browser page loading the same Mermaid version.
2. Compare per-node width/height and centre position. Report max and median deviation, in px and
   as a fraction of node size.
3. Judge whether the deviation is visible at TMT's zoom levels.

**Artifact.** A deviation table, and a recommendation on the default backend.

**Design implication either way.** Make the renderer pluggable (`--renderer mermaidx|mmdc`), and
have the CLI record which renderer and Mermaid version produced a layout in the layout JSON
provenance block. Do not let the preview path and the conversion path diverge silently — if
`mmdc` is chosen as the fidelity default, document that `mermaidx` is the fast path for CI and
may shift node sizes slightly.

---

## A5 — TM7 connector geometry

**Question.** What exactly does TMT do with `SourceX/Y`, `TargetX/Y`, `HandleX/Y`, and how
should a dagre polyline be reduced to it?

**Method.**

1. In TMT, draw a flow, drag its handle to several positions, save, diff the XML each time.
   Establish whether the handle is a quadratic control point, a point on the curve, or something
   else.
2. Determine whether `SourceX/Y` and `TargetX/Y` are absolute canvas coordinates or offsets, and
   whether TMT recomputes them from the connected elements on open (i.e. whether writing them
   even matters).
3. Test candidate reductions of a Mermaid path against the visual result:
   - midpoint by arc length
   - the bend point furthest from the straight source→target chord
   - centroid of interior bend points
4. Check behaviour for self-loops and for two parallel flows between the same element pair —
   confirm they do not render on top of each other.

**Artifact.** A recommended reduction function with screenshots comparing Mermaid path vs TMT
rendering for the routing fixtures.

---

## A6 — Boundary containment semantics

**Question.** Does TMT determine which elements are inside a trust boundary purely geometrically,
and what tolerance applies at the edges?

**Why it matters.** The Markdown model asserts logical containment; the SVG gives geometry. If
the two disagree — e.g. Mermaid draws a cluster rect that clips a node by 1px — TMT may
associate the element with the wrong boundary, which changes generated threats. This is a
correctness issue, not a cosmetic one.

**Method.**

1. Construct a TM7 where an element straddles a boundary edge; open in TMT and inspect which
   threats are generated.
2. Test partial overlap at 10%, 50%, 90% to find the rule (centre-in? full containment? any
   overlap?).
3. Test nested boundaries — which boundary wins for an element inside both.

**Artifact.** The containment rule, plus a required padding/epsilon value for the mapper.

**Design implication.** The mapper must **validate** logical containment from the Markdown
against geometric containment from the SVG and fail loudly on mismatch (see
`04-tm7-mapping-spec.md` §Validation).

---

## A7 — Node id round-tripping

**Question.** How does Mermaid sanitize node ids into SVG `id` attributes, and can we guarantee
a reliable reverse mapping?

**Method.** Render fixtures with ids containing hyphens, underscores, dots, digits-first,
unicode, and very long ids. Record input id → `flowchart-<x>-<n>` output. Determine what the
trailing counter is (render order? per-diagram index?) and whether it is stable across renders
of the same source.

**Design implication.** Since the tool generates the Mermaid source from its own model, it
controls the ids. Prefer constraining generated ids to a safe charset (`[A-Za-z][A-Za-z0-9_]*`)
over reverse-engineering the sanitizer. **Never match nodes by label text** — labels are not
unique and may be user-edited.

---

## A8 — Scale factor between Mermaid px and TMT canvas

**Question.** Is a 1:1 pixel copy readable in TMT, or is a uniform scale needed?

**Method.** Convert a medium fixture at scale 1.0, 1.25 and 1.5; open each in TMT and compare
against the Mermaid preview at 100% zoom. Consider that TMT draws thicker strokes and its own
label text, which needs more room than Mermaid's.

**Artifact.** A recommended default for `--scale`, and a recommended default for
`flowchart.nodeSpacing` / `rankSpacing` overrides to inject into the Mermaid config so that
converted diagrams breathe.

---

## A9 — Existing prior art

**Question.** Has anyone already built Mermaid-geometry → TM7, or SVG-geometry → any DFD format?

**Method.** Search GitHub and PyPI for: `tm7` converters, `mermaid` → `drawio`/`diagrams.net`
geometry extractors, `svg` → graph-model extractors. Known adjacent projects worth reading:
`Part-IO/TMT2Cairis` (TM7 → diagrams.net XML — inspect how it handles coordinates),
`schutzwerk/tmte4pt`, `TMTool` on PyPI, `matthiasrohr/OTMT` (sample TM7 files).

**Artifact.** A short note on anything reusable, especially TM7 XML writers that already get the
`DataContractSerializer` quirks right.

---

## Exit criteria

The investigation is complete when:

- [ ] A1 confirmed, with per-stencil size behaviour documented
- [ ] A2 selectors documented and pinned to a specific Mermaid version
- [ ] A3 normalization implemented with a passing rasterization cross-check
- [ ] A4 deviation quantified and a default renderer chosen
- [ ] A5 handle reduction chosen with visual evidence
- [ ] A6 containment rule documented with a required epsilon
- [ ] A7 id policy decided
- [ ] A8 default scale chosen
- [ ] Fixture SVGs committed for the pinned Mermaid version
