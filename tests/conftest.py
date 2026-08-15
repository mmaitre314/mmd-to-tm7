from __future__ import annotations

import importlib.metadata as md
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MMD_DIR = FIXTURES / "mermaid"
LAYOUT_DIR = FIXTURES / "layout"


def renderer_tag() -> str:
    try:
        return f"mermaidx-{md.version('mermaidx')}"
    except md.PackageNotFoundError:
        return "mermaidx-unknown"


def svg_dir() -> Path:
    return FIXTURES / "svg" / renderer_tag()


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


def fixture_names() -> list[str]:
    return sorted(p.stem for p in MMD_DIR.glob("*.mmd"))


@pytest.fixture(params=fixture_names())
def fixture_name(request) -> str:
    return request.param
