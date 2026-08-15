"""Exception hierarchy for mermaid2tm7.

Callers (including the skill's ``tm7_cli.py``) can distinguish causes by catching
the specific subclass. See ``docs/05-package-and-cli-spec.md`` §Errors.
"""

from __future__ import annotations


class Mermaid2Tm7Error(Exception):
    """Base class for every error raised by this package."""


class RendererUnavailableError(Mermaid2Tm7Error):
    """A renderer backend cannot run (missing mermaidx, Node, or Chromium)."""


class MermaidSyntaxError(Mermaid2Tm7Error):
    """The Mermaid source failed to parse; wraps the renderer's own message."""


class ExtractionError(Mermaid2Tm7Error):
    """The rendered SVG did not match the expected structure.

    This usually means the Mermaid version changed. The message should tell the
    user to run ``mermaid2tm7 doctor``.
    """


class LayoutValidationError(Mermaid2Tm7Error):
    """Layout JSON failed schema validation or a geometry sanity check."""


class MappingError(Mermaid2Tm7Error):
    """The Markdown model and the layout geometry disagree.

    Raised for containment mismatches, missing elements, and unresolved flows.
    """
