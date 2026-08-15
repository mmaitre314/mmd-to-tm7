"""mermaidx renderer backend — the default, no Node/browser required.

``mermaidx`` runs the real Mermaid library inside QuickJS-ng against a fake DOM,
bridging text metrics from a bundled font. Fast and hermetic; node sizes may
differ slightly from a browser preview (spike A4).
"""

from __future__ import annotations

import importlib.metadata as _md

from ...errors import MermaidSyntaxError, RendererUnavailableError


class MermaidxRenderer:
    name = "mermaidx"

    def __init__(self) -> None:
        self._mermaidx = None

    def _load(self):
        if self._mermaidx is None:
            try:
                import mermaidx
            except ImportError as exc:
                raise RendererUnavailableError(
                    "The 'mermaidx' package is not installed. Install it with "
                    "`pip install mermaidx` (no Node or browser required)."
                ) from exc
            self._mermaidx = mermaidx
        return self._mermaidx

    def available(self) -> bool:
        try:
            self._load()
            return True
        except RendererUnavailableError:
            return False

    def version(self) -> str:
        try:
            return _md.version("mermaidx")
        except _md.PackageNotFoundError:  # pragma: no cover
            return "unknown"

    def mermaid_version(self) -> str:
        """The Mermaid library version bundled in mermaidx.

        mermaidx does not expose this directly as an API, so we read it from the
        SVG (``aria-roledescription="flowchart-v2"``) is not enough; we return the
        best available signal. Pinned and recorded in provenance regardless.
        """
        mermaidx = self._load()
        for attr in ("MERMAID_VERSION", "mermaid_version", "__mermaid_version__"):
            v = getattr(mermaidx, attr, None)
            if v:
                return str(v)
        return f"bundled-in-mermaidx-{self.version()}"

    def render(self, source: str, config: dict | None = None) -> str:
        mermaidx = self._load()
        try:
            diagram = mermaidx.render(source)
            return diagram.svg()
        except RendererUnavailableError:
            raise
        except Exception as exc:  # mermaidx raises generic errors on bad syntax
            raise MermaidSyntaxError(
                f"mermaidx failed to render the Mermaid source: {exc}"
            ) from exc
