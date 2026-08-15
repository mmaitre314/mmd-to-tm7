"""Parse Markdown + Mermaid into a semantic :class:`Model`.

In the full skill, the model comes from ``tm7_cli.py``'s own parser. This module
is the self-contained equivalent that lets ``mermaid2tm7`` run end-to-end from a
single ``.md``/``.mmd`` file. It parses the Mermaid *source text* (not the rendered
SVG) so that **logical** containment — the subgraph nesting the author wrote — is
captured independently of geometry, which is exactly what the mapper cross-checks
against the SVG (``docs/04-tm7-mapping-spec.md`` §Validation, spike A6).

Shape -> stencil mapping (documented default; override by supplying a Model directly):

    [(  )]  cylinder   -> data store
    >(  )] / [/ /]      -> external interactor
    ((  ))  circle      -> process
    [[  ]]  subroutine  -> multi-process
    everything else     -> process
"""

from __future__ import annotations

import re

from .model import Boundary, Element, ElementType, Flow, Model

_MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)


def extract_mermaid_block(text: str, index: int = 0) -> str:
    """Return the ``index``-th ```mermaid fenced block, or the text itself if none."""
    blocks = _MERMAID_BLOCK_RE.findall(text)
    if not blocks:
        # treat the whole input as a bare .mmd diagram
        return text
    if index >= len(blocks):
        raise IndexError(f"diagram index {index} out of range ({len(blocks)} mermaid blocks)")
    return blocks[index]


# node token: id + optional shape-wrapped label
_NODE_RE = re.compile(
    r"""(?P<id>[A-Za-z0-9_.-]+)\s*
        (?:
          \[\(\s*(?P<cyl>[^\)]*?)\s*\)\]      # [( )] cylinder
        | \(\(\s*(?P<circ>[^\)]*?)\s*\)\)     # (( )) circle
        | \[\[\s*(?P<sub>[^\]]*?)\s*\]\]      # [[ ]] subroutine
        | \{\{\s*(?P<hex>[^\}]*?)\s*\}\}      # {{ }} hexagon
        | \{\s*(?P<rhomb>[^\}]*?)\s*\}        # {  } diamond
        | \(\[\s*(?P<stad>[^\]]*?)\s*\]\)     # ([ ]) stadium
        | \[\/\s*(?P<par>[^\]]*?)\s*\/\]      # [/ /] parallelogram -> external
        | \(\s*(?P<round>[^\)]*?)\s*\)        # ( ) rounded
        | \[\s*(?P<rect>[^\]]*?)\s*\]         # [ ] rect
        )?
    """,
    re.VERBOSE,
)

# A Mermaid link operator, optionally carrying an inline |label|.
_ARROW_RE = re.compile(
    r"""(?P<arrow>
          <?(?:-\.-+|-{2,3}|={2,3})[->ox]?   # -->, ---, ==>, -.->, <--, --o, --x
        )
        (?:\s*\|\s*(?P<label>[^|]*?)\s*\|)?    # optional |label| after the arrow
    """,
    re.VERBOSE,
)

# leading node token of an operand: id + optional shape-wrapped label.
# No '^' anchor: we use Pattern.match(line, pos), which already anchors at pos
# (and '^' would only match at true string start, breaking A --> B chains).
_OPERAND_RE = re.compile(r"\s*" + _NODE_RE.pattern, re.VERBOSE)

_SUBGRAPH_RE = re.compile(
    r"^\s*subgraph\s+(?P<id>[A-Za-z0-9_.-]+)\s*(?:\[\s*(?P<label>[^\]]*?)\s*\])?\s*$"
)
_DIR_RE = re.compile(r"\b(?:flowchart|graph)\s+(LR|RL|TB|BT|TD)\b", re.IGNORECASE)
_KEYWORDS = {"subgraph", "end", "flowchart", "graph", "direction", "classDef", "class", "style", "linkStyle"}


def _label_and_type(m: re.Match) -> tuple[str | None, ElementType, bool]:
    """Return (label, element_type, is_shape) for a node match."""
    for grp, etype in (
        ("cyl", ElementType.DATA_STORE),
        ("par", ElementType.EXTERNAL_INTERACTOR),
        ("sub", ElementType.MULTI_PROCESS),
        ("circ", ElementType.PROCESS),
        ("hex", ElementType.EXTERNAL_INTERACTOR),
        ("rhomb", ElementType.PROCESS),
        ("stad", ElementType.PROCESS),
        ("round", ElementType.PROCESS),
        ("rect", ElementType.PROCESS),
    ):
        val = m.group(grp)
        if val is not None:
            return (val or None), etype, True
    return None, ElementType.PROCESS, False


def _parse_statement(line: str, ensure_element, model: Model) -> None:
    """Parse one flowchart statement: a node declaration or an edge chain.

    Splits the line on link operators and takes each operand's leading node
    token, so a labelled source (``A[Label] --> B``) is handled correctly.
    """
    operands: list[tuple[str, str | None, ElementType, bool]] = []
    arrow_labels: list[str | None] = []
    pos = 0
    while pos < len(line):
        om = _OPERAND_RE.match(line, pos)
        if not om or not om.group("id"):
            break
        nid = om.group("id")
        if nid in _KEYWORDS:
            break
        label, etype, typed = _label_and_type(om)
        operands.append((nid, label, etype, typed))
        pos = om.end()
        am = _ARROW_RE.match(line, _skip_ws(line, pos))
        if not am:
            break
        arrow_labels.append(am.group("label"))
        pos = am.end()

    for nid, label, etype, typed in operands:
        ensure_element(nid, label, etype, typed)
    for i in range(len(operands) - 1):
        src = operands[i][0]
        dst = operands[i + 1][0]
        lbl = arrow_labels[i] if i < len(arrow_labels) else None
        model.flows.append(Flow(source=src, target=dst, name=lbl or ""))


def _skip_ws(s: str, pos: int) -> int:
    while pos < len(s) and s[pos] in " \t":
        pos += 1
    return pos


def parse_model(text: str, *, model_id: str | None = None, diagram_index: int = 0) -> Model:
    """Parse Markdown/Mermaid ``text`` into a :class:`Model`."""
    diagram = extract_mermaid_block(text, diagram_index)
    lines = diagram.splitlines()

    model = Model(id=model_id or "model", title="Threat Model")
    elements: dict[str, Element] = {}
    boundaries: dict[str, Boundary] = {}
    stack: list[str] = []  # current subgraph nesting

    def ensure_element(nid: str, label: str | None, etype: ElementType, typed: bool) -> None:
        parent = stack[-1] if stack else None
        if nid in elements:
            el = elements[nid]
            if typed:
                el.type = etype
                if label:
                    el.name = label
            if el.parent is None and parent is not None:
                el.parent = parent
        else:
            elements[nid] = Element(
                id=nid, name=label or nid, type=etype, parent=parent
            )

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue

        sg = _SUBGRAPH_RE.match(raw)
        if sg:
            bid = sg.group("id")
            boundaries.setdefault(
                bid,
                Boundary(
                    id=bid,
                    name=sg.group("label") or bid,
                    parent=stack[-1] if stack else None,
                ),
            )
            stack.append(bid)
            continue
        if line == "end":
            if stack:
                stack.pop()
            continue
        first = line.split()[0]
        if first in _KEYWORDS and not _ARROW_RE.search(line):
            # pure directive (flowchart LR, direction, classDef, ...)
            continue

        _parse_statement(line, ensure_element, model)

    model.elements = list(elements.values())
    model.boundaries = list(boundaries.values())
    return model


def direction_of(text: str, diagram_index: int = 0) -> str:
    diagram = extract_mermaid_block(text, diagram_index)
    m = _DIR_RE.search(diagram)
    if not m:
        return "TB"
    d = m.group(1).upper()
    return "TB" if d == "TD" else d
