"""Renderer protocol and shared helpers.

Implements the pluggable backend contract from ``docs/03-svg-extraction-spec.md``
§Renderer backends. Backends must fail loudly when unavailable and never fall
back to one another silently, because that would change geometry without the
user knowing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Renderer(Protocol):
    name: str

    def version(self) -> str:
        """Version of the renderer backend itself."""
        ...

    def mermaid_version(self) -> str:
        """Version of the Mermaid library the backend drives."""
        ...

    def available(self) -> bool:
        """True if this backend can run in the current environment."""
        ...

    def render(self, source: str, config: dict | None = None) -> str:
        """Render Mermaid ``source`` to SVG text. Raises on unavailability/syntax."""
        ...
