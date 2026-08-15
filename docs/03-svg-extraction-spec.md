# Mermaid SVG → Layout JSON

Implements `mermaid2tm7.extract`. Input: a Mermaid flowchart source string. Output: layout JSON
per `02-layout-json-spec.md`.

**Everything in this file is provisional until spikes A2, A3 and A7 in `01-investigation.md`
confirm the actual DOM structure of the pinned Mermaid version.** Treat the selectors below as a
starting hypothesis to verify, not as ground truth.

## Pipeline

```
mermaid source
  → inject config (§Config injection)
  → render to SVG (§Renderer backends)
  → parse XML
  → build transform tree (§Transform normalization)
  → extract nodes, clusters, edges
  → flatten edge paths (§Path flattening)
  → derive containment (§Containment)
  → normalize origin
  → validate against JSON Schema
  → layout JSON
```

## Renderer backends

Pluggable via a small protocol:

```python
class Renderer(Protocol):
    name: str
    def version(self) -> str: ...
    def mermaid_version(self) -> str: ...
    def render(self, source: str, config: dict) -> str: ...  # returns SVG text
```

Two implementations:

- **`MermaidxRenderer`** — `pip install mermaidx`; `mermaidx.render(source, config=...).svg()`.
  No Node, no browser, fast. Uses a bundled font for text metrics, so node sizes may differ
  slightly from a browser (spike A4).
- **`MmdcRenderer`** — shells out to `@mermaid-js/mermaid-cli`. Requires Node and a Chromium
  download. Browser-accurate; matches what the user sees in a VS Code preview.

Default backend is decided by spike A4. Whichever is chosen, the other must remain available via
`--renderer`, and the choice is recorded in `provenance`.

Both renderers must fail with a clear, actionable error when unavailable (missing Node, missing
Chromium, unparseable Mermaid source) — never fall back silently to the other renderer, because
that would silently change geometry.

## Config injection

Before rendering, merge a config block into the source. Purpose: pin behaviour that affects
geometry so output is reproducible.

```yaml
config:
  layout: dagre          # explicit; do not inherit a user's elk setting silently
  look: classic
  theme: default         # theme affects padding in some versions — pin it
  flowchart:
    padding: <configurable>
    nodeSpacing: <configurable, default from spike A8>
    rankSpacing: <configurable, default from spike A8>
    htmlLabels: false    # prefer <text> over foreignObject if it simplifies extraction — VERIFY in A2
    curve: linear        # straight segments are far easier to flatten and reduce than basis curves
```

Two of these deserve attention during the spikes:

- `htmlLabels: false` may change how labels are measured and therefore node sizes. If it changes
  geometry relative to what the user previews, do **not** set it — extraction convenience does
  not justify breaking fidelity.
- `curve: linear` similarly. If the user's preview uses the default basis curve and we render
  with linear, node positions are unchanged but edge paths differ. Since only three points of
  each path survive into TM7, this is likely acceptable — confirm during A5 and document.

If the user's Markdown already contains a config front-matter block, merge rather than replace,
and warn on conflicts.

## Transform normalization

Do not regex `translate(...)`. Parse the full SVG transform grammar (`translate`, `scale`,
`rotate`, `matrix`, `skewX`, `skewY`, whitespace/comma variants) into 2×3 affine matrices and
compose down the ancestor chain.

```python
@dataclass(frozen=True)
class Affine:
    a: float; b: float; c: float; d: float; e: float; f: float
    def __matmul__(self, other: "Affine") -> "Affine": ...
    def apply(self, x: float, y: float) -> tuple[float, float]: ...

def parse_transform(s: str) -> Affine: ...
def ctm_for(element) -> Affine:  # composed ancestor transforms, root-first
```

Then account for the `viewBox`: if `viewBox="minX minY w h"` has a non-zero origin, subtract it.

**Required cross-check test** (see A3): rasterize the SVG to PNG (`mermaidx.svg_to_raw`) and
assert every computed node centre lands on non-background pixels inside the shape. This catches
transform bugs that unit tests on synthetic SVG will not.

## Node extraction

Hypothesis to verify:

- Select `g.node` elements (typically under `g.nodes`), each with `id="flowchart-<id>-<n>"`
- The element's composed transform gives the node **centre**
- The first child shape (`rect`, `polygon`, `path`, `circle`, `ellipse`) gives the size:
  - `rect`: `width`/`height` attributes
  - `circle`: `2*r`
  - `polygon`/`path`: compute the bounding box of the geometry
- Convert centre + size → top-left corner

Map `svg_id` back to the Mermaid node id. Per spike A7, prefer *controlling* the ids at
generation time to a safe charset over reverse-engineering Mermaid's sanitizer. Implement the
reverse map as: strip the `flowchart-` prefix and the trailing `-<digits>` counter, then match
against the known set of ids from the Markdown model. **Error out on any node that cannot be
mapped** — a silently dropped node is a missing element in the threat model.

Also assert node count parity: number of `g.node` elements == number of nodes in the model.

## Cluster extraction

Hypothesis to verify:

- Select `g.cluster` elements, each with `id` equal to the subgraph id
- A child `rect` carries `x`, `y`, `width`, `height`; apply the composed transform to `(x, y)`
- Nesting: determine `parent` geometrically (smallest strictly-containing cluster) and record
  `depth`

Mermaid may render a cluster label inside the top of the rect. That label band is part of the
rect, and TMT boundaries also reserve space for a name, so no adjustment should be needed —
confirm visually.

## Path flattening

Parse the `d` attribute properly (`M`, `L`, `C`, `Q`, `S`, `T`, `A`, `Z`, absolute and relative).
Consider `svgpathtools` or `svg.path` rather than hand-rolling; if a dependency is unwelcome,
implement `M`/`L`/`C` only and error on anything else, since Mermaid emits a narrow subset.

Flatten curves by adaptive subdivision to a flatness tolerance of ~0.5px, capped at 64 points per
segment. Then simplify with Ramer–Douglas–Peucker at ~1px epsilon so `points` stays readable.

## Handle point reduction

One documented function, chosen by spike A5:

```python
def reduce_to_handle(points: list[Point]) -> Point | None:
    """Reduce a flattened edge polyline to a single TM7 curve handle."""
```

Candidate strategies to implement and compare behind a `--handle-strategy` flag during
development, then hard-code the winner:

- `arclength_mid` — point at 50% of cumulative arc length
- `max_deviation` — interior point furthest from the straight source→target chord
- `bend_centroid` — centroid of interior bend points

Special cases:

- Fewer than 3 points → return `None`; the mapper writes a straight flow
- Self-loops (source == target) → the reduction must produce a handle that makes the loop
  visible; verify in TMT
- Parallel edges between the same pair → handles must differ, or TMT stacks them; if the
  reduction produces near-identical handles, offset them perpendicular to the chord and emit a
  warning

## Containment

For each node and cluster, `parent` = the smallest cluster whose rect strictly contains the box.
Use a tolerance of `EPS` (default 1.0px) to absorb rounding.

If a box overlaps a cluster boundary without being contained (partial overlap beyond `EPS`),
emit a `cluster_clips_node` warning with the overlap magnitude. The mapper decides whether that
is fatal (see A6 — it may change which threats TMT generates).

## Errors

Fail loudly, with the Mermaid source line where possible:

| Condition | Behaviour |
|---|---|
| Renderer unavailable | Error naming the missing dependency and the install command |
| Mermaid parse error | Surface Mermaid's own message verbatim |
| Node count mismatch model vs SVG | Error |
| Unmappable `svg_id` | Error, listing the unmapped ids |
| Unsupported path command | Error |
| Partial cluster overlap | Warning (error under `--strict`) |
| Zero-area node or cluster | Error |
