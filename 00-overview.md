# mermaid2tm7 — Overview and Design Decisions

## Context

[`mmaitre314/threat-modeling-skill`](https://github.com/mmaitre314/threat-modeling-skill) is an AI skill that
authors `.tm7` files for the Microsoft Threat Modeling Tool (TMT). It uses an intermediate
Markdown + Mermaid format as the human-editable source, and `tm7_cli.py generate` converts that
Markdown into TM7.

The current TM7 generator computes element coordinates itself using a hand-written compound
layered layout (see `docs/tm7-layout-investigation.md`, `docs/graph-layout-algorithm-comparison.md`,
`docs/tm7-layout-implementation-sketch.md`). That layout is adequate for small diagrams and
degrades badly on complex ones — overlapping shapes, crossing connectors, boundaries that no
longer read as groupings.

## Goal

**The TM7 diagram should be geometrically identical to what the user already sees in their
Mermaid preview.** The intended workflow is:

1. User iterates on the Markdown + Mermaid model until the diagram reads well in preview.
2. User converts to TM7.
3. User opens the TM7 in TMT and needs to make **little or no** layout adjustment.

This is a *fidelity* goal, not a *layout quality* goal. Layout quality becomes the user's problem
to solve in Mermaid, where they already have fast iteration and a live preview. We stop trying
to be a layout engine.

## Decision: read Mermaid's rendered SVG

Mermaid's layout is not "dagre". Dagre is one step in a pipeline:

1. Parse flowchart → node/edge objects
2. Measure each label by rendering it into a DOM and calling `getBBox()`, then add
   shape-specific padding → node width/height
3. Recursive subgraph handling — lay out clusters, re-insert them as nodes in the parent graph,
   re-route edges that cross cluster borders
4. Dagre
5. Post-process — clip edges to shape boundary intersections, interpolate curves (d3-shape),
   place edge labels

Options considered:

| Approach | Fidelity to Mermaid | Effort | Verdict |
|---|---|---|---|
| Keep hand-written layout | None | already built | Current state; the problem |
| Reimplement dagre in Python | Approximate — misses steps 2, 3, 5 | High | Rejected |
| Embed `dagre.js` in QuickJS, drive it ourselves | Approximate — same gap | Medium | Rejected |
| Call ELK (`elkjs`) directly with TMT stencil sizes | None (different engine) | Medium | Rejected *for this goal*; keep as a future `--engine elk` option if fidelity is ever dropped as a requirement |
| **Parse Mermaid's own rendered SVG** | **Exact by construction** | **Medium** | **Chosen** |

Note: there is no usable Python port of dagre. `dagre-py` on PyPI is a plotting wrapper around
`dagre-d3` and does not expose layout coordinates.

## Consequence: TM7 elements take Mermaid's sizes, not TMT stencil defaults

The usual objection to reusing Mermaid coordinates is that Mermaid sizes nodes to fit label text
while TMT stencils have fixed default dimensions (~100×100). Placing fixed-size stencils at
text-fitted coordinates produces overlaps for short labels and gaps for long ones.

Under the fidelity goal this dissolves: copy Mermaid's node width and height into the TM7
element's `Width`/`Height` as well as its position. TMT elements are resizable on canvas, so a
1:1 geometric copy should be expressible.

**This is assumption A1 and must be verified before implementation — see `01-investigation.md`.**

## What "look the same" can and cannot mean

Achievable:

- Node positions and sizes — exact
- Trust boundary rectangles — exact
- Which elements fall inside which boundary — exact (follows from the above)
- Overall canvas proportions and reading direction

Not achievable, by design or by TM7 limitation:

- **Shape appearance.** TMT draws its own stencils (process = circle, data store = parallel
  lines, etc.). A Mermaid rounded rectangle becomes a TMT stencil occupying the same bounding
  box. This is expected and desirable.
- **Multi-bend connector routing.** A TM7 data flow stores `SourceX/Y`, `TargetX/Y` and a single
  `HandleX/HandleY` — one curve handle. Dagre polylines that route around a cluster collapse to
  a single curve. This is the largest fidelity gap and it is a TM7 format limitation, not
  something to engineer around. Expect manual fixup here on dense diagrams.
- **Edge label placement.** TMT positions the flow name itself; Mermaid's `edgeLabel` coordinate
  cannot be pinned.

## Deliverable

A standalone, pip-installable Python package with a CLI, consumable both by a human and by
`tm7_cli.py`:

```
mermaid2tm7 layout   --input model.md  --output layout.json   # extract geometry only
mermaid2tm7 generate --input model.md  --output model.tm7     # full conversion
```

The package is deliberately separable from the skill so the geometry pipeline can be tested
independently of TM7 semantics. Integration into `tm7_cli.py generate` is via a new
`--engine svg|builtin` flag, with `builtin` retained as the fallback for environments where no
Mermaid renderer is available.

## Non-goals

- Improving on Mermaid's layout quality
- Round-tripping TM7 → Mermaid geometry (existing `parse` command is unaffected)
- Supporting Mermaid diagram types other than `flowchart` / `graph`
- Pixel-matching TMT's rendering of shapes or text

## Spec files

| File | Purpose |
|---|---|
| `00-overview.md` | This file — context, decisions, scope |
| `01-investigation.md` | Spikes to run **before** writing production code; each has an explicit question, method, and artifact |
| `02-layout-json-spec.md` | The intermediate geometry format — the contract between extraction and mapping |
| `03-svg-extraction-spec.md` | Mermaid SVG → layout JSON |
| `04-tm7-mapping-spec.md` | Layout JSON → TM7 |
| `05-package-and-cli-spec.md` | Package layout, CLI surface, Python API, renderer backends |
| `06-testing-spec.md` | Fixtures, golden tests, validation, metrics, CI |

## How to use these specs

`01-investigation.md` comes first and is not optional. Several load-bearing assumptions in the
later specs are marked `ASSUMPTION Ax` and are *unverified*. If a spike falsifies one, stop and
report rather than working around it — some falsifications (notably A1) invalidate the whole
approach and should send us back to the ELK option.
