# Testing

The risk profile here is unusual: the code is not algorithmically hard, but it depends on an
undocumented DOM structure that changes without notice, and on a proprietary file format whose
renderer we cannot script. Tests should be weighted accordingly — heavy on committed fixtures and
cross-checks, light on unit tests of trivial logic.

## Fixture corpus

The A2 fixture set from `01-investigation.md` is permanent test data. Under
`tests/fixtures/mermaid/`:

| Fixture | Exercises |
|---|---|
| `flat.mmd` | baseline, no clusters |
| `single_cluster.mmd` | boundary rect, edges crossing it |
| `nested_clusters.mmd` | two-level nesting, z-order, containment |
| `label_extremes.mmd` | very short and very long labels — the node-sizing case |
| `all_shapes.mmd` | every shape the skill emits |
| `edge_cases.mmd` | labelled, bidirectional, self-loop, parallel edges |
| `cross_cluster.mmd` | edges between two different clusters |
| `direction_lr.mmd` / `direction_tb.mmd` | same graph, both directions |
| `azure_vm.mmd` | the real sample from the repo — the realistic case |
| `large.mmd` | 40+ nodes, 5+ boundaries — the case that motivated this work |

## Test layers

**1. Unit — deterministic, no rendering**

- `test_transforms.py` — transform parsing and composition against hand-computed matrices,
  including `matrix()`, negative `viewBox` origins, nested groups
- `test_paths.py` — path parsing, curve flattening tolerance, RDP simplification
- `test_handles.py` — each reduction strategy against hand-drawn polylines; degenerate cases
  (2 points, self-loop, collinear)

**2. Extraction golden tests — SVG in, layout JSON out**

Committed SVGs under `tests/fixtures/svg/<mermaid-version>/` are the input, so these tests do not
require a renderer and are fast and hermetic. Compare against committed layout JSON with a
tolerance of ±0.5px on coordinates. A diff means either an extractor regression or a deliberate
change requiring fixture regeneration — the review should show *why*.

**3. Raster cross-check** (`test_raster_crosscheck.py`)

For each fixture: rasterize the SVG (`mermaidx.svg_to_raw`), and assert every extracted node
centre lands on non-background pixels, and every cluster rect corner is near a drawn line. This
is the test that actually catches transform bugs — the golden tests only prove we are
consistently wrong.

**4. Renderer tests — Mermaid source in, SVG out** (marked `@pytest.mark.renderer`)

Re-render each fixture and assert the SVG still matches the expected *structure* (selectors
present, node count correct) — not byte equality. When this fails, Mermaid has changed and the
fixtures need regenerating. Run these on a schedule as well as on PRs, so drift is caught before
a user reports it.

**5. Mapping golden tests — layout JSON in, TM7 out**

Committed TM7 outputs, compared after normalizing anything nondeterministic (timestamps; Guids
should be deterministic per `04-tm7-mapping-spec.md`, so if they are not stable, that is itself a
bug this test should catch).

**6. TM7 deserialization** (marked `@pytest.mark.windows`)

Every generated TM7 must pass `tools/tm7_validate.exe`, which uses TMT's own
`DataContractSerializer` types. Skip with an explicit message off Windows; do not let the skip
read as a pass.

**7. Fidelity metrics** (`test_metrics.py`)

Quantitative regression guards, asserted as thresholds rather than exact values:

| Metric | Target |
|---|---|
| Node overlap area (sum of pairwise intersections) | 0 |
| Elements outside their assigned boundary | 0 |
| Logical vs geometric containment mismatches | 0 |
| Edge crossings | record; assert no worse than the committed baseline |
| Position deviation vs the source SVG, after inverse transform | < 1px |

Also run these against the `builtin` engine on the same fixtures and record both. That gives a
concrete, defensible answer to "is this actually better?" and protects against the new path
regressing below the old one on some fixture class.

## Manual verification protocol

Some things cannot be automated, because TMT is a Windows GUI with no scripting surface. Define a
short checklist to run before each release, with screenshots committed to `docs/`:

1. Convert `azure_vm.mmd` and `large.mmd`
2. Open each in TMT alongside the Mermaid preview at comparable zoom
3. Confirm: no overlapping shapes; every element visually inside the right boundary; boundaries
   not obscuring elements; flows visually traceable; labels legible
4. Record how many manual adjustments would be needed to make it presentable — **this number is
   the actual success metric for the project.** Target: zero for `azure_vm`, low single digits
   for `large`

Track that number across releases. Everything else in this spec exists to serve it.

## CI

```yaml
jobs:
  test:            # ubuntu, python 3.10–3.13 — units, extraction goldens, raster cross-check, mapping
  renderer:        # ubuntu + node — renderer tests with both mermaidx and mmdc
  validate-tm7:    # windows + .NET 4.8 — tm7_validate.exe over generated outputs
  drift:           # scheduled weekly — re-render fixtures against latest mermaid, report structural diffs
```

The `drift` job is the important one and the easiest to skip. It is what turns "a Mermaid update
silently broke everyone's diagrams" into "we got a failing scheduled build."
