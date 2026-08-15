# Layout JSON — the extraction/mapping contract

A single intermediate format sits between "read geometry out of Mermaid" and "write TM7". This
keeps the fragile part (SVG parsing, which tracks Mermaid's internals) separate from the
semantic part (TM7 mapping, which tracks Microsoft's format), and makes both independently
testable with committed fixtures.

It is also useful on its own: `mermaid2tm7 layout` emits it, so the geometry can be inspected or
fed to a different backend (draw.io, SVG re-render, a future ELK path) later.

## Coordinate conventions

- Origin top-left, y increases downward, units are pixels
- All coordinates are in **one flat space** — cluster children are *not* parent-relative
- Node `x`, `y` are the **top-left corner** of the bounding box, not the centre. (Mermaid's SVG
  uses centres; the extractor converts. This matches TM7's `Left`/`Top` and avoids a second
  conversion in the mapper.)
- The extractor normalizes so that `min(x) == 0` and `min(y) == 0` across all nodes and clusters,
  then records the applied offset in `canvas.origin_offset` for debugging

## Schema

```jsonc
{
  "version": "1",

  "provenance": {
    "mermaid_version": "11.14.0",
    "renderer": "mermaidx",           // "mermaidx" | "mmdc"
    "renderer_version": "0.8.1",
    "source_sha256": "…",             // hash of the Mermaid source that was rendered
    "generated_at": "2026-08-15T00:00:00Z"
  },

  "canvas": {
    "width": 1240.5,
    "height": 860.0,
    "origin_offset": { "x": -12.0, "y": -8.0 },
    "direction": "LR"                 // "LR" | "RL" | "TB" | "BT", from the Mermaid source
  },

  "nodes": [
    {
      "id": "webapp",                 // Mermaid node id, as written in the source
      "svg_id": "flowchart-webapp-3",
      "label": "Web App",             // text content, newlines normalized to \n
      "shape": "rounded",             // "rect" | "rounded" | "stadium" | "circle" | "cylinder" | "hexagon" | "diamond" | "unknown"
      "x": 120.0, "y": 40.0,
      "width": 148.0, "height": 54.0,
      "parent": "tb_azure"            // enclosing cluster id, or null
    }
  ],

  "clusters": [
    {
      "id": "tb_azure",
      "svg_id": "tb_azure",
      "label": "Azure Subscription",
      "x": 80.0, "y": 10.0,
      "width": 640.0, "height": 420.0,
      "parent": null,                 // enclosing cluster id for nesting, or null
      "depth": 0                      // 0 = outermost; convenience for z-ordering
    }
  ],

  "edges": [
    {
      "id": "L_browser_webapp_0",
      "source": "browser",            // Mermaid node ids, never svg_ids
      "target": "webapp",
      "label": "HTTPS",               // or null
      "label_pos": { "x": 300.0, "y": 120.0 },   // or null
      "points": [ [90.0, 67.0], [104.0, 67.0], [120.0, 67.0] ],
      "start_point": [90.0, 67.0],    // == points[0], duplicated for convenience
      "end_point": [120.0, 67.0],     // == points[-1]
      "handle_point": [104.0, 67.0]   // reduction of `points` per 01-investigation A5
    }
  ],

  "warnings": [
    { "code": "cluster_clips_node", "detail": "node 'kv' extends 2.1px beyond cluster 'tb_azure'" }
  ]
}
```

## Field notes

**`nodes[].shape`** is informational only. Element type in TM7 comes from the Markdown model, not
from the Mermaid shape. It is recorded for debugging and for a possible future consistency check
(model says data store, Mermaid draws a cylinder → good; model says data store, Mermaid draws a
diamond → the Markdown generator has a bug).

**`nodes[].parent` and `clusters[].parent`** are derived geometrically by the extractor (smallest
cluster fully containing the box) and must be cross-checked against the logical structure in the
Markdown by the mapper. Disagreement is an error, not something to silently resolve — see
`04-tm7-mapping-spec.md`.

**`edges[].points`** is the flattened polyline of the SVG path `d`. Bezier segments are sampled;
see `03-svg-extraction-spec.md` §Path flattening. This is the full fidelity record. TM7 can only
use three of these points, but keeping the whole path means a future format or a smarter
reduction can use it, and it makes the reduction independently testable.

**`edges[].handle_point`** is computed by the extractor, not the mapper, so that the reduction
strategy is a single documented function with its own tests. It may be null for degenerate paths
(fewer than 3 points).

**`warnings`** is for non-fatal geometry oddities. The CLI prints them; `--strict` promotes them
to errors.

## Stability

The layout JSON is a versioned public artifact. Bump `version` on any breaking change. Consumers
must ignore unknown fields.

## Validation

Ship a JSON Schema at `mermaid2tm7/schemas/layout-v1.json` and validate on both write and read.
This catches extractor regressions at the boundary rather than deep inside the TM7 writer.
