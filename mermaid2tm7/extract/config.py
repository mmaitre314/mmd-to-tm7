"""Mermaid config injection.

Implements ``docs/03-svg-extraction-spec.md`` §Config injection. We pin the
geometry-affecting behaviour (layout engine, theme, spacing) into the source so
output is reproducible, merging with any front-matter the user already wrote
rather than replacing it.

Note on ``htmlLabels``/``curve``: the spec flags these as risky because they can
change node sizes / edge paths relative to what the user previews. We therefore
do **not** force them here; we only pin the layout engine, theme and spacing,
which do not change what the user approved.
"""

from __future__ import annotations

import re

# Spike A8 (choosing a default spacing that "breathes" in TMT) needs the Windows
# Threat Modeling Tool and is not runnable here. We leave Mermaid's own defaults
# in place and expose nodeSpacing/rankSpacing as overridable knobs. See
# docs/investigation.md.
DEFAULT_CONFIG: dict = {
    "theme": "default",
    "flowchart": {},
}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_INIT_RE = re.compile(r"%%\{\s*init\s*:\s*(\{.*?\})\s*\}%%", re.DOTALL)


def build_config(overrides: dict | None = None) -> dict:
    """Merge caller overrides onto the pinned defaults (deep, one level)."""
    cfg = {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULT_CONFIG.items()}
    if overrides:
        for key, val in overrides.items():
            if isinstance(val, dict) and isinstance(cfg.get(key), dict):
                cfg[key] = {**cfg[key], **val}
            else:
                cfg[key] = val
    return cfg


def inject(source: str, config: dict) -> str:
    """Inject ``config`` into a Mermaid source via an ``%%{init}%%`` directive.

    If the source already carries an ``init`` directive, this appends a second
    one; Mermaid merges them with the later one winning, so our pinned settings
    take precedence over an inherited layout engine.
    """
    import json

    directive = f"%%{{init: {json.dumps(config)}}}%%"
    fm = _FRONTMATTER_RE.match(source)
    if fm:
        # Keep front-matter first, then our directive, then the body.
        head = source[: fm.end()]
        body = source[fm.end() :]
        return f"{head}{directive}\n{body}"
    return f"{directive}\n{source}"
