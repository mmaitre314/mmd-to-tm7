"""Read/write layout JSON with schema validation on both directions.

Implements ``docs/02-layout-json-spec.md`` §Validation: validating on write catches
extractor regressions at the boundary, before the TM7 writer runs; validating on
read protects the mapper from a hand-edited or stale file.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from ..errors import LayoutValidationError
from .model import Layout

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "layout-v1.json"


@functools.lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_dict(data: dict[str, Any]) -> None:
    """Validate a layout dict against the JSON Schema.

    Falls back to a minimal structural check if ``jsonschema`` is not installed,
    so the package still functions (with weaker guarantees) in a bare environment.
    """
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - depends on environment
        _minimal_check(data)
        return
    try:
        jsonschema.validate(data, _schema())
    except jsonschema.ValidationError as exc:
        raise LayoutValidationError(
            f"layout JSON failed schema validation at {list(exc.absolute_path)}: {exc.message}"
        ) from exc


def _minimal_check(data: dict[str, Any]) -> None:
    for key in ("version", "provenance", "canvas", "nodes", "clusters", "edges"):
        if key not in data:
            raise LayoutValidationError(f"layout JSON missing required key {key!r}")
    if data.get("version") != "1":
        raise LayoutValidationError(f"unsupported layout version {data.get('version')!r}")


def dumps(layout: Layout, *, indent: int = 2) -> str:
    data = layout.to_dict()
    validate_dict(data)
    return json.dumps(data, indent=indent)


def write(layout: Layout, path: str | Path) -> None:
    Path(path).write_text(dumps(layout), encoding="utf-8")


def loads(text: str) -> Layout:
    data = json.loads(text)
    validate_dict(data)
    return Layout.from_dict(data)


def read(path: str | Path) -> Layout:
    return loads(Path(path).read_text(encoding="utf-8"))
