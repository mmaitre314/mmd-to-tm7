# Layout JSON → TM7

Implements `mermaid2tm7.mapping`. Inputs: the parsed Markdown model (element types, names,
properties, flow semantics — already produced by the existing `tm7_cli.py` parser) **and** the
layout JSON (geometry only). Output: a `.tm7` file.

The split is deliberate. **Semantics come from the Markdown; geometry comes from the SVG.**
Neither source is consulted for the other's job.

## Coordinate transform

```
X_tm7 = round((x_layout + margin_x) * scale)
Y_tm7 = round((y_layout + margin_y) * scale)
W_tm7 = round(width_layout  * scale)
H_tm7 = round(height_layout * scale)
```

- `scale` — default from spike A8, overridable via `--scale`
- `margin_x`, `margin_y` — default 40px pre-scale, so the diagram is not flush against the TMT
  canvas edge
- Round to integers if TM7 requires them; verify whether the format accepts floats (it is
  `DataContractSerializer` XML, so the field type governs) and prefer whatever TMT itself writes

Apply the *same* scale to `HandleX/Y`, `SourceX/Y`, `TargetX/Y`.

## Element mapping

For each node in the layout JSON, find the corresponding model element by id and emit a TM7
element with:

| TM7 field | Source |
|---|---|
| `Guid` | Stable, derived — see §Guid stability |
| `GenericTypeId` / `TypeId` | Model element type (unchanged from current generator) |
| Properties (Name, description, stencil properties) | Model (unchanged) |
| `Left` | `X_tm7` |
| `Top` | `Y_tm7` |
| `Width` | `W_tm7` — **new**, was previously a stencil default |
| `Height` | `H_tm7` — **new** |

Clamp `Width`/`Height` to the min/max TMT accepts, per spike A1. If a clamp fires, emit a
warning naming the element, because the resulting diagram will no longer match the preview at
that spot.

## Boundary mapping

Each cluster becomes a `BorderBoundary` with `Left`/`Top`/`Width`/`Height` from the cluster rect.

Z-ordering matters: TMT renders in document order, so boundaries must be written **before** the
elements they contain, outermost first. Use `clusters[].depth` to sort. Verify by opening a
nested-boundary output in TMT — if elements are hidden behind a boundary fill, the order is
wrong.

Line boundaries (`LineBoundary`) have no Mermaid equivalent and are out of scope. If the Markdown
model can express one, keep whatever the current generator does and document the gap.

## Connector (data flow) mapping

For each edge:

| TM7 field | Source |
|---|---|
| `SourceGuid` | Guid of the source element |
| `TargetGuid` | Guid of the target element |
| `SourceX`, `SourceY` | `edges[].start_point`, transformed |
| `TargetX`, `TargetY` | `edges[].end_point`, transformed |
| `HandleX`, `HandleY` | `edges[].handle_point`, transformed; if null, the chord midpoint |
| Name, properties | Model |

Per spike A5, confirm whether TMT recomputes `SourceX/Y` and `TargetX/Y` from the connected
elements when opening the file. If it does, writing them is harmless but pointless, and only the
handle matters.

## Guid stability

Guids should be **deterministic across runs** so that regenerating a TM7 after an edit produces a
minimal diff and, more importantly, so that threat state and mitigations recorded against
elements survive regeneration. Use UUIDv5 with a fixed namespace:

```python
GUID_NS = uuid.UUID("…fixed namespace for this tool…")
element_guid = uuid.uuid5(GUID_NS, f"{model_id}:{element_id}")
flow_guid    = uuid.uuid5(GUID_NS, f"{model_id}:{source_id}->{target_id}:{ordinal}")
```

Check what the current generator does first — if it already has a scheme, keep it. If it emits
random Guids, changing this is a compatibility event for anyone with existing models, so flag it
rather than deciding unilaterally. Note that `update-threats` already round-trips threat state,
so there may be an established mechanism to respect.

## Validation

Run before writing, and fail on any error:

**Structural**

- Every model element appears exactly once in the layout JSON, and vice versa
- Every flow's source and target resolve to emitted elements

**Containment (spike A6)** — the important one:

- For each element, geometric parent (from layout JSON) == logical parent (from the Markdown's
  subgraph structure). A mismatch means TMT will generate threats for a different trust boundary
  crossing than the model describes. **Error, not warning.**
- Every element's box is fully inside its boundary's box with at least `EPS` margin, after
  scaling. If Mermaid's cluster rect clips a node, either grow the boundary by the shortfall
  (preferred, and emit a warning) or error under `--strict`.

**Geometric sanity**

- No two element boxes overlap by more than `OVERLAP_TOL` (default 0)
- All coordinates positive after margin
- Canvas within whatever bounds TMT tolerates

## Output verification

The repo already has `tools/tm7_validate.exe`, which validates deserialization using TMT's own
`DataContractSerializer` types. Every generated file in the test suite must pass it. On
non-Windows CI, skip with a clear message rather than silently passing.

## Integration with the existing skill

Add to `tm7_cli.py generate`:

```
--engine svg|builtin     default: svg if a renderer is available, else builtin with a warning
--renderer mermaidx|mmdc
--scale FLOAT
--layout-json PATH       write the intermediate layout JSON alongside the TM7, for debugging
--strict
```

Keep `builtin` working. It is the fallback for air-gapped environments and the control case for
comparing layout quality.

Update `SKILL.md` so the AI agent knows: iterate on the Mermaid until the preview looks right,
because the preview *is* the TM7 layout now. That is a real change in how the skill should
behave — previously the Mermaid was documentation and the layout was computed; now the Mermaid
is authoritative.
