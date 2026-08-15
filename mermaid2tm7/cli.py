"""Command-line interface for mermaid2tm7.

Commands (``docs/05-package-and-cli-spec.md`` §CLI):

    mermaid2tm7 layout   --input <model.md|diagram.mmd> --output layout.json
    mermaid2tm7 generate --input <model.md> --output model.tm7
    mermaid2tm7 render   --input <model.md> --output preview.svg
    mermaid2tm7 doctor
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .errors import Mermaid2Tm7Error
from .extract import extract_layout
from .extract.config import build_config, inject
from .extract.renderers import available_renderers, get_renderer
from .layout import io as layout_io
from .tm7 import generate_tm7, parse_model
from .tm7.markdown import extract_mermaid_block


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _common_extract(args) -> object:
    text = _read(args.input)
    mermaid_src = extract_mermaid_block(text, args.diagram_index)
    known = None
    try:
        known = parse_model(text, diagram_index=args.diagram_index).element_ids()
    except Exception:
        known = None
    return extract_layout(
        mermaid_src,
        renderer=args.renderer,
        strict=args.strict,
        known_ids=known,
    )


def cmd_layout(args) -> int:
    layout = _common_extract(args)
    out = layout_io.dumps(layout)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(out)
    _print_warnings(layout.warnings, args.verbose)
    return 0


def cmd_generate(args) -> int:
    text = _read(args.input)
    model = parse_model(
        text, model_id=args.model_id or Path(args.input).stem, diagram_index=args.diagram_index
    )
    layout = extract_layout(
        extract_mermaid_block(text, args.diagram_index),
        renderer=args.renderer,
        strict=args.strict,
        known_ids=model.element_ids(),
    )
    if args.layout_json:
        layout_io.write(layout, args.layout_json)
        print(f"wrote {args.layout_json}", file=sys.stderr)
    warnings = generate_tm7(
        model, layout, args.output, scale=args.scale, margin=args.margin, strict=args.strict
    )
    print(f"wrote {args.output}", file=sys.stderr)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def cmd_render(args) -> int:
    text = _read(args.input)
    mermaid_src = extract_mermaid_block(text, args.diagram_index)
    cfg = build_config()
    backend = get_renderer(args.renderer)
    svg = backend.render(inject(mermaid_src, cfg), cfg)
    if args.output:
        Path(args.output).write_text(svg, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(svg)
    return 0


def cmd_doctor(args) -> int:
    print(f"mermaid2tm7 {__version__}")
    print("renderers:")
    for name, ok in available_renderers().items():
        status = "available" if ok else "UNAVAILABLE"
        line = f"  {name}: {status}"
        if ok:
            b = get_renderer(name)
            try:
                line += f"  (v{b.version()}, mermaid {b.mermaid_version()})"
            except Exception as exc:  # pragma: no cover
                line += f"  (version probe failed: {exc})"
        print(line)
    validate_exe = Path("tools/tm7_validate.exe")
    print(f"tm7_validate.exe: {'present' if validate_exe.exists() else 'absent'}")
    try:
        import jsonschema  # noqa: F401

        print("jsonschema: present")
    except ImportError:
        print("jsonschema: absent (layout validation falls back to a minimal check)")
    return 0


def _print_warnings(warnings, verbose: bool) -> None:
    for w in warnings:
        print(f"warning: {w.code}: {w.detail}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mermaid2tm7", description=__doc__)
    p.add_argument("--version", action="version", version=f"mermaid2tm7 {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp, *, renderer=True, strict=True):
        sp.add_argument("--input", "-i", required=True, help="Markdown or .mmd file")
        sp.add_argument("--diagram-index", type=int, default=0, help="which mermaid block")
        if renderer:
            sp.add_argument("--renderer", choices=["mermaidx", "mmdc"], default="mermaidx")
        if strict:
            sp.add_argument("--strict", action="store_true", help="promote warnings to errors")
        sp.add_argument("-v", "--verbose", action="store_true")

    sp = sub.add_parser("layout", help="extract geometry only")
    add_common(sp)
    sp.add_argument("--output", "-o", help="layout JSON path (stdout if omitted)")
    sp.set_defaults(func=cmd_layout)

    sp = sub.add_parser("generate", help="full conversion to TM7")
    add_common(sp)
    sp.add_argument("--output", "-o", required=True, help="output .tm7 path")
    sp.add_argument("--scale", type=float, default=1.0)
    sp.add_argument("--margin", type=int, default=40)
    sp.add_argument("--layout-json", help="also dump intermediate layout JSON")
    sp.add_argument("--model-id", help="stable model id for deterministic Guids")
    sp.set_defaults(func=cmd_generate)

    sp = sub.add_parser("render", help="dump the exact SVG we extract from")
    add_common(sp, strict=False)
    sp.add_argument("--output", "-o", help="SVG path (stdout if omitted)")
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("doctor", help="report renderers and environment")
    sp.set_defaults(func=cmd_doctor)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Mermaid2Tm7Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
