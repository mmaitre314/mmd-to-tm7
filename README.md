# mermaid2tm7

Convert a [Mermaid](https://mermaid.js.org/) flowchart's **rendered geometry** into a
Microsoft Threat Modeling Tool (`.tm7`) file, so the threat model you open in TMT is
geometrically identical to the Mermaid preview you already iterated on.

Instead of reimplementing Mermaid's layout, `mermaid2tm7` renders the diagram to SVG
with the real Mermaid library, reads the node/cluster/edge coordinates back out, and
copies that geometry — positions **and** text-fitted sizes — into TM7. Layout quality
becomes something you solve in Mermaid, where you have a live preview.

See [`docs/00-overview.md`](docs/00-overview.md) for the full design rationale.

## Install

```bash
pip install mermaid2tm7
```

The default renderer is [`mermaidx`](https://pypi.org/project/mermaidx/) — the real
Mermaid library running inside QuickJS-ng, so **no Node or browser is required**. For
browser-accurate rendering that matches a VS Code Markdown preview, install
`@mermaid-js/mermaid-cli` (Node + Chromium) and pass `--renderer mmdc`.

## CLI

```bash
mermaid2tm7 generate --input model.md  --output model.tm7    # full conversion
mermaid2tm7 layout   --input model.md  --output layout.json  # geometry only
mermaid2tm7 render   --input model.md  --output preview.svg  # the exact SVG we extract from
mermaid2tm7 doctor                                           # report renderers + versions
```

Common flags: `--renderer mermaidx|mmdc`, `--scale FLOAT`, `--margin INT`,
`--strict`, `--layout-json PATH`, `--diagram-index INT`.

`render` exists to diagnose "TMT doesn't look like my preview": it isolates a renderer
mismatch from an extraction bug by showing exactly the SVG being converted.

## Python API

```python
from mermaid2tm7 import extract_layout, generate_tm7, parse_model

source = open("model.md").read()
model  = parse_model(source, model_id="my-model")
layout = extract_layout(source, renderer="mermaidx")

for node in layout.nodes:
    print(node.id, node.x, node.y, node.width, node.height)

generate_tm7(model, layout, "model.tm7", scale=1.0)
```

`extract_layout` is usable entirely on its own — it has no TM7 dependency and emits the
versioned [layout JSON](docs/02-layout-json-spec.md), which is handy for feeding a
different backend.

## How it works

```
Markdown + Mermaid
  ├─ parse_model ─────────────► semantic Model (element types, names, boundaries, flows)
  └─ render to SVG ─► extract ─► Layout JSON (geometry: positions, sizes, edge points)
                                    │
                    Model + Layout ─┴─► map ─► model.tm7
```

- **Semantics come from the Markdown; geometry comes from the SVG.** Neither source is
  consulted for the other's job.
- The mapper **validates** that the boundary each element sits in geometrically matches
  the subgraph the author wrote it into, and errors on a mismatch — because that would
  change which trust-boundary crossings TMT generates threats for.
- Guids are deterministic (UUIDv5) so regenerating after an edit is a minimal diff and
  threat state recorded against elements survives.

## Supported Mermaid version

The extractor's SVG selectors are pinned to the Mermaid version bundled in
`mermaidx==0.9.4`. Mermaid layout changes across minor versions silently move diagrams,
so the version is recorded in every layout JSON's `provenance`, and the package warns
when converting a layout produced by a different version. `mermaid2tm7 doctor` reports
what you have installed.

## Status and limitations

This package is the **geometry pipeline**, which is fully implemented and tested here
(unit tests, hermetic SVG→layout golden tests, and a raster cross-check that verifies
the transform math against actual rendered pixels).

Several items require the Windows-only Threat Modeling Tool and were **not** verifiable
in the development environment — see [`docs/investigation.md`](docs/investigation.md):

- Whether TMT honours arbitrary element `Width`/`Height` (assumed yes; spike A1).
- Validating generated `.tm7` files with `tools/tm7_validate.exe` (spike / output
  verification). The TM7 writer follows the documented format but has not been
  round-tripped through TMT.
- Tuning connector handles (A5) and scale/margins (A8) against TMT's rendering.

When integrating into the [`threat-modeling-skill`](https://github.com/mmaitre314/threat-modeling-skill),
reconcile `tm7/writer.py` and the Guid scheme with that repo's existing `tm7_cli.py`
generator, and add `--engine svg` alongside the retained `builtin` fallback.

## Not achievable by design

TMT draws its own stencils (a process is a circle, a data store is parallel lines), so
shape *appearance* differs — that is expected. A TM7 data flow stores a single curve
handle, so multi-bend dagre routes collapse to one curve; expect manual fixup on dense
diagrams. Edge-label placement is controlled by TMT and cannot be pinned.

## License

MIT. Mermaid and `mermaidx` are MIT.
