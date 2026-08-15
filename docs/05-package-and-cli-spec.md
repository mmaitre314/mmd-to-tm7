# Package, CLI and API

## Why a separate package

`mermaid2tm7` ships independently of the skill so that:

- the geometry pipeline can be tested without TM7 semantics in the way
- it is useful to people who want Mermaid → TM7 without the AI skill
- the skill's dependency surface stays small — the skill depends on the package, not the reverse

The skill's `tm7_cli.py` imports it and adds `--engine svg`.

## Layout

```
mermaid2tm7/
  __init__.py
  cli.py                      # argparse/typer entry point
  extract/
    __init__.py
    renderers/
      base.py                 # Renderer protocol
      mermaidx_renderer.py
      mmdc_renderer.py
    transforms.py             # affine parsing/composition
    paths.py                  # SVG path parsing, flattening, RDP simplification
    handles.py                # polyline → single handle reduction
    svg.py                    # the extractor itself
  layout/
    model.py                  # dataclasses mirroring layout JSON
    io.py                     # read/write + schema validation
  tm7/
    writer.py                 # TM7 XML emission
    mapping.py                # layout JSON + model → TM7
    guids.py
  schemas/
    layout-v1.json
  py.typed
tests/
  fixtures/
    mermaid/                  # .mmd inputs (the A2 fixture set)
    svg/<mermaid-version>/    # committed rendered SVGs
    layout/                   # committed expected layout JSON
    tm7/                      # committed expected TM7
  test_transforms.py
  test_paths.py
  test_handles.py
  test_extract.py
  test_mapping.py
  test_golden.py
  test_raster_crosscheck.py
docs/
  investigation.md            # spike findings from 01-investigation.md
pyproject.toml
README.md
```

## Dependencies

Core:

- `mermaidx` — default renderer, no Node required
- an SVG path parser (`svgpathtools` or `svg.path`) — or hand-rolled M/L/C if avoiding the dep
- `jsonschema` for layout validation
- stdlib `xml.etree` for both SVG parsing and TM7 writing (`lxml` only if namespace handling
  proves painful — TM7's `DataContractSerializer` XML is namespace-heavy)

Optional extras:

- `[mmdc]` — documents the Node + `@mermaid-js/mermaid-cli` requirement; the renderer shells out
  so there is no Python dep, but the extra can carry a check script
- `[dev]` — pytest, ruff, mypy

## Mermaid version pinning

Layout changes across Mermaid v11 minors will silently move every user's diagram. The package
must:

1. Pin `mermaidx` to an exact version, and record the Mermaid version it bundles
2. Record `mermaid_version` in every layout JSON's `provenance`
3. Warn when converting a layout JSON produced by a different Mermaid version than the one
   currently installed
4. Document the supported Mermaid version range in the README, and tell users which VS Code
   preview extension version matches

Treat a Mermaid bump as a minor version bump of this package with regenerated golden fixtures and
a visual review of the diffs.

## CLI

```
mermaid2tm7 layout   --input <model.md|diagram.mmd> --output layout.json
mermaid2tm7 generate --input <model.md> --output model.tm7
mermaid2tm7 render   --input <model.md> --output preview.svg   # the exact SVG we extract from
mermaid2tm7 doctor                                             # report available renderers + versions
```

Common flags:

| Flag | Default | Notes |
|---|---|---|
| `--renderer mermaidx\|mmdc` | per spike A4 | recorded in provenance |
| `--scale FLOAT` | per spike A8 | |
| `--margin INT` | 40 | pre-scale, in Mermaid px |
| `--strict` | off | promote geometry warnings to errors |
| `--layout-json PATH` | — | on `generate`, also dump the intermediate |
| `--diagram-index INT` | 0 | which ```mermaid block in the Markdown |
| `-v/--verbose` | | |

`render` exists so users can see *exactly* the geometry being converted, which is the fastest way
to diagnose "TMT doesn't look like my preview" reports — it isolates renderer mismatch (A4) from
extraction bugs.

`doctor` reports: installed renderers, their versions, the bundled Mermaid version, whether Node
and Chromium are reachable, and whether `tm7_validate.exe` is present. Make support cheap.

## Python API

```python
from mermaid2tm7 import extract_layout, generate_tm7, Layout

layout: Layout = extract_layout(
    mermaid_source,
    renderer="mermaidx",
    config={"flowchart": {"nodeSpacing": 60}},
)

for node in layout.nodes:
    print(node.id, node.x, node.y, node.width, node.height)

generate_tm7(model, layout, output_path="model.tm7", scale=1.25)
```

Keep `extract_layout` usable without any TM7 involvement — it is the piece most likely to be
useful to someone else, and keeping it decoupled is what makes it testable.

## Errors

Define a small exception hierarchy so callers (including `tm7_cli.py`) can distinguish causes:

```
Mermaid2Tm7Error
├── RendererUnavailableError      # missing Node/Chromium/mermaidx
├── MermaidSyntaxError            # wraps Mermaid's own message
├── ExtractionError               # DOM shape not as expected — likely a Mermaid version change
├── LayoutValidationError         # schema or geometry sanity failure
└── MappingError                  # model/layout disagreement, containment mismatch
```

`ExtractionError` should say so explicitly: *"The rendered SVG does not match the expected
structure for Mermaid 11.x. This usually means the Mermaid version changed. Run
`mermaid2tm7 doctor`."* That single message will save most of the future support burden.

## Licensing

Mermaid is MIT; `mermaidx` is MIT; the skill repo is MIT. No conflict. If ELK is ever added as an
alternative engine, note that `elkjs` is EPL-2.0 — file-level copyleft, fine to bundle alongside
MIT code, but worth a NOTICE entry.
