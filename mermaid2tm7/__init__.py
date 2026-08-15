"""mermaid2tm7 — convert a Mermaid flowchart's rendered geometry into a TM7 file.

The core idea (``docs/00-overview.md``): the TM7 diagram should be geometrically
identical to the user's Mermaid preview. We read Mermaid's own rendered SVG rather
than reimplementing its layout, extract a renderer-agnostic *layout JSON*, then map
that geometry plus the Markdown model's semantics into a ``.tm7``.

High-level API::

    from mermaid2tm7 import extract_layout, generate_tm7, parse_model

    layout = extract_layout(mermaid_source, renderer="mermaidx")
    model = parse_model(markdown_source, model_id="my-model")
    generate_tm7(model, layout, "model.tm7", scale=1.0)
"""

from __future__ import annotations

from .errors import (
    ExtractionError,
    LayoutValidationError,
    MappingError,
    Mermaid2Tm7Error,
    MermaidSyntaxError,
    RendererUnavailableError,
)
from .extract import extract_layout, extract_layout_from_svg
from .layout.model import Layout
from .tm7 import Model, generate_tm7, parse_model

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "extract_layout",
    "extract_layout_from_svg",
    "generate_tm7",
    "parse_model",
    "Layout",
    "Model",
    "Mermaid2Tm7Error",
    "RendererUnavailableError",
    "MermaidSyntaxError",
    "ExtractionError",
    "LayoutValidationError",
    "MappingError",
]
