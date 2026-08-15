"""Renderer backends for mermaid2tm7."""

from __future__ import annotations

from ...errors import RendererUnavailableError
from .base import Renderer
from .mermaidx_renderer import MermaidxRenderer
from .mmdc_renderer import MmdcRenderer

__all__ = ["Renderer", "MermaidxRenderer", "MmdcRenderer", "get_renderer", "available_renderers"]

_REGISTRY = {
    "mermaidx": MermaidxRenderer,
    "mmdc": MmdcRenderer,
}


def get_renderer(name: str = "mermaidx") -> Renderer:
    """Instantiate a renderer by name. Never falls back silently to another."""
    try:
        cls = _REGISTRY[name]
    except KeyError:
        raise RendererUnavailableError(
            f"unknown renderer {name!r}; choose from {sorted(_REGISTRY)}"
        ) from None
    return cls()


def available_renderers() -> dict[str, bool]:
    """Map of renderer name -> availability, for `doctor`."""
    return {name: cls().available() for name, cls in _REGISTRY.items()}
