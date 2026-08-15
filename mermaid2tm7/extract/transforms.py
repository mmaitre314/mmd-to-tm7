"""SVG affine transforms — parsing and composition.

Implements ``docs/03-svg-extraction-spec.md`` §Transform normalization. We parse
the full SVG transform grammar into 2x3 affine matrices rather than regexing
``translate(...)``, because cluster and node groups can in principle carry
``matrix()`` or ``scale()`` and a regex silently drops those.

Matrix convention (same as SVG / CSS):

    | a c e |   | x |
    | b d f | * | y |
    | 0 0 1 |   | 1 |

so a point (x, y) maps to (a*x + c*y + e, b*x + d*y + f).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Affine:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    @staticmethod
    def identity() -> Affine:
        return Affine()

    @staticmethod
    def translate(tx: float, ty: float = 0.0) -> Affine:
        return Affine(e=tx, f=ty)

    @staticmethod
    def scale(sx: float, sy: float | None = None) -> Affine:
        return Affine(a=sx, d=sx if sy is None else sy)

    @staticmethod
    def rotate(deg: float, cx: float = 0.0, cy: float = 0.0) -> Affine:
        r = math.radians(deg)
        cos, sin = math.cos(r), math.sin(r)
        rot = Affine(a=cos, b=sin, c=-sin, d=cos)
        if cx == 0.0 and cy == 0.0:
            return rot
        return Affine.translate(cx, cy) @ rot @ Affine.translate(-cx, -cy)

    def __matmul__(self, other: Affine) -> Affine:
        """Matrix product ``self @ other`` (apply ``other`` first, then ``self``)."""
        return Affine(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            e=self.a * other.e + self.c * other.f + self.e,
            f=self.b * other.e + self.d * other.f + self.f,
        )

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)


_FUNC_RE = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")
_NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _nums(s: str) -> list[float]:
    return [float(m.group(0)) for m in _NUM_RE.finditer(s)]


def parse_transform(s: str | None) -> Affine:
    """Parse an SVG ``transform`` attribute into a composed :class:`Affine`.

    Multiple functions compose left-to-right the same way the SVG spec applies
    them: the leftmost is outermost. Unknown/empty input yields the identity.
    """
    if not s:
        return Affine.identity()
    result = Affine.identity()
    for func, args in _FUNC_RE.findall(s):
        n = _nums(args)
        if func == "matrix" and len(n) == 6:
            m = Affine(*n)
        elif func == "translate":
            m = Affine.translate(n[0], n[1] if len(n) > 1 else 0.0)
        elif func == "scale":
            m = Affine.scale(n[0], n[1] if len(n) > 1 else None)
        elif func == "rotate":
            if len(n) == 3:
                m = Affine.rotate(n[0], n[1], n[2])
            else:
                m = Affine.rotate(n[0])
        elif func == "skewX":
            m = Affine(c=math.tan(math.radians(n[0])))
        elif func == "skewY":
            m = Affine(b=math.tan(math.radians(n[0])))
        else:
            continue
        result = result @ m
    return result


def ctm_for(element: object, parents: list[object]) -> Affine:
    """Composed transform matrix for ``element``, root-first.

    ``parents`` is the ancestor chain from the SVG root down to (but excluding)
    ``element``. Each object must expose a ``get("transform")`` method like an
    ``xml.etree`` element.
    """
    ctm = Affine.identity()
    for node in [*parents, element]:
        t = node.get("transform")  # type: ignore[attr-defined]
        if t:
            ctm = ctm @ parse_transform(t)
    return ctm
