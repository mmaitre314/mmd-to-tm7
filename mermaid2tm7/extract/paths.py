"""SVG path parsing, curve flattening and RDP simplification.

Implements ``docs/03-svg-extraction-spec.md`` §Path flattening. Mermaid emits a
narrow subset of the path grammar (``M``, ``L``, ``C`` and occasionally ``A``
for cylinder/self-loop shapes). We parse M/L/C/Q/S/T/Z fully and raise on
anything else so a Mermaid change that introduces new commands is caught rather
than silently mis-flattened.
"""

from __future__ import annotations

import math
import re

Point = tuple[float, float]

# Capture any alpha as a command token so unknown letters reach the else branch
# and raise, rather than being silently dropped (docs/03 §Path flattening).
_TOKEN_RE = re.compile(r"([A-Za-z])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")


class PathParseError(ValueError):
    """A path command we do not support (e.g. arcs, if ever emitted for edges)."""


def _tokenize(d: str) -> list[str]:
    return [m.group(1) or m.group(2) for m in _TOKEN_RE.finditer(d)]


def _cubic(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    mt = 1.0 - t
    a, b, c, dd = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
    return (
        a * p0[0] + b * p1[0] + c * p2[0] + dd * p3[0],
        a * p0[1] + b * p1[1] + c * p2[1] + dd * p3[1],
    )


def _flatten_cubic(
    p0: Point, p1: Point, p2: Point, p3: Point, tol: float, cap: int
) -> list[Point]:
    """Adaptively subdivide a cubic Bezier to ``tol`` flatness, capped at ``cap`` pts."""
    n = max(2, min(cap, _cubic_segments(p0, p1, p2, p3, tol)))
    return [_cubic(p0, p1, p2, p3, i / n) for i in range(1, n + 1)]


def _cubic_segments(p0: Point, p1: Point, p2: Point, p3: Point, tol: float) -> int:
    # Estimate subdivisions from control-point deviation from the chord.
    d1 = _point_line_dist(p1, p0, p3)
    d2 = _point_line_dist(p2, p0, p3)
    dev = max(d1, d2)
    if dev <= tol:
        return 2
    import math

    return int(math.ceil(math.sqrt(dev / tol) * 4))


def _point_line_dist(p: Point, a: Point, b: Point) -> float:
    import math

    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 == 0.0:
        return math.hypot(px - ax, py - ay)
    return abs((px - ax) * dy - (py - ay) * dx) / math.sqrt(seg2)


def _flatten_arc(
    cur: Point,
    rx: float,
    ry: float,
    phi_deg: float,
    large: int,
    sweep: int,
    end: Point,
    cap: int = 32,
) -> list[Point]:
    """Flatten an SVG elliptical-arc segment to points (endpoint parameterization)."""
    x1, y1 = cur
    x2, y2 = end
    if (x1 == x2 and y1 == y2) or rx == 0 or ry == 0:
        return [end]
    phi = math.radians(phi_deg)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    rx, ry = abs(rx), abs(ry)
    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cos_p * dx2 + sin_p * dy2
    y1p = -sin_p * dx2 + cos_p * dy2
    # correct out-of-range radii
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp = coef * rx * y1p / ry
    cyp = -coef * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2.0
    cy = sin_p * cxp + cos_p * cyp + (y1 + y2) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        length = math.hypot(ux, uy) * math.hypot(vx, vy) or 1.0
        a = math.acos(max(-1.0, min(1.0, dot / length)))
        if ux * vy - uy * vx < 0:
            a = -a
        return a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi
    n = max(2, min(cap, int(abs(dtheta) / (math.pi / 16)) + 1))
    out: list[Point] = []
    for i in range(1, n + 1):
        t = theta1 + dtheta * i / n
        px = cos_p * rx * math.cos(t) - sin_p * ry * math.sin(t) + cx
        py = sin_p * rx * math.cos(t) + cos_p * ry * math.sin(t) + cy
        out.append((px, py))
    return out


def parse_path(
    d: str, *, flatten_tol: float = 0.5, cap: int = 64, allow_arcs: bool = False
) -> list[Point]:
    """Parse a path ``d`` string into a flattened polyline.

    Supports M/L/H/V/C/S/Q/T/Z (absolute and relative). Arcs (``A``) are rejected
    by default and raise :class:`PathParseError` — Mermaid edge paths never use
    them, so an arc signals a Mermaid change. Node *shapes* (cylinder, stadium)
    do use arcs; those call with ``allow_arcs=True`` to get a flattened bbox.
    """
    toks = _tokenize(d)
    i = 0
    pts: list[Point] = []
    cur: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    prev_cubic_ctrl: Point | None = None
    prev_quad_ctrl: Point | None = None
    cmd = ""

    def num() -> float:
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
        rel = cmd.islower()
        C = cmd.upper()

        if C == "M":
            x, y = num(), num()
            cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
            start = cur
            pts.append(cur)
            cmd = "l" if rel else "L"  # subsequent pairs are implicit lineto
            prev_cubic_ctrl = prev_quad_ctrl = None
        elif C == "L":
            x, y = num(), num()
            cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
            pts.append(cur)
            prev_cubic_ctrl = prev_quad_ctrl = None
        elif C == "H":
            x = num()
            cur = (cur[0] + x, cur[1]) if rel else (x, cur[1])
            pts.append(cur)
            prev_cubic_ctrl = prev_quad_ctrl = None
        elif C == "V":
            y = num()
            cur = (cur[0], cur[1] + y) if rel else (cur[0], y)
            pts.append(cur)
            prev_cubic_ctrl = prev_quad_ctrl = None
        elif C == "C":
            x1, y1, x2, y2, x, y = (num() for _ in range(6))
            p1 = (cur[0] + x1, cur[1] + y1) if rel else (x1, y1)
            p2 = (cur[0] + x2, cur[1] + y2) if rel else (x2, y2)
            p3 = (cur[0] + x, cur[1] + y) if rel else (x, y)
            pts.extend(_flatten_cubic(cur, p1, p2, p3, flatten_tol, cap))
            cur, prev_cubic_ctrl, prev_quad_ctrl = p3, p2, None
        elif C == "S":
            x2, y2, x, y = (num() for _ in range(4))
            p1 = (2 * cur[0] - prev_cubic_ctrl[0], 2 * cur[1] - prev_cubic_ctrl[1]) if prev_cubic_ctrl else cur
            p2 = (cur[0] + x2, cur[1] + y2) if rel else (x2, y2)
            p3 = (cur[0] + x, cur[1] + y) if rel else (x, y)
            pts.extend(_flatten_cubic(cur, p1, p2, p3, flatten_tol, cap))
            cur, prev_cubic_ctrl, prev_quad_ctrl = p3, p2, None
        elif C == "Q":
            x1, y1, x, y = (num() for _ in range(4))
            q = (cur[0] + x1, cur[1] + y1) if rel else (x1, y1)
            p3 = (cur[0] + x, cur[1] + y) if rel else (x, y)
            # elevate quadratic to cubic
            p1 = (cur[0] + 2 / 3 * (q[0] - cur[0]), cur[1] + 2 / 3 * (q[1] - cur[1]))
            p2 = (p3[0] + 2 / 3 * (q[0] - p3[0]), p3[1] + 2 / 3 * (q[1] - p3[1]))
            pts.extend(_flatten_cubic(cur, p1, p2, p3, flatten_tol, cap))
            cur, prev_quad_ctrl, prev_cubic_ctrl = p3, q, None
        elif C == "T":
            x, y = num(), num()
            q = (2 * cur[0] - prev_quad_ctrl[0], 2 * cur[1] - prev_quad_ctrl[1]) if prev_quad_ctrl else cur
            p3 = (cur[0] + x, cur[1] + y) if rel else (x, y)
            p1 = (cur[0] + 2 / 3 * (q[0] - cur[0]), cur[1] + 2 / 3 * (q[1] - cur[1]))
            p2 = (p3[0] + 2 / 3 * (q[0] - p3[0]), p3[1] + 2 / 3 * (q[1] - p3[1]))
            pts.extend(_flatten_cubic(cur, p1, p2, p3, flatten_tol, cap))
            cur, prev_quad_ctrl, prev_cubic_ctrl = p3, q, None
        elif C == "Z":
            pts.append(start)
            cur = start
            prev_cubic_ctrl = prev_quad_ctrl = None
        elif C == "A":
            rx, ry, rot, large, sweep, x, y = (num() for _ in range(7))
            if not allow_arcs:
                raise PathParseError(
                    "Arc command 'A' in edge path is not supported; Mermaid edges "
                    "normally emit only M/L/C. This may indicate a Mermaid change."
                )
            end = (cur[0] + x, cur[1] + y) if rel else (x, y)
            pts.extend(_flatten_arc(cur, rx, ry, rot, int(large), int(sweep), end, cap))
            cur = end
            prev_cubic_ctrl = prev_quad_ctrl = None
        else:
            raise PathParseError(f"Unsupported path command {cmd!r}")
    return pts


def rdp(points: list[Point], epsilon: float = 1.0) -> list[Point]:
    """Ramer-Douglas-Peucker simplification to ``epsilon`` px."""
    if len(points) < 3:
        return list(points)
    dmax, index = 0.0, 0
    a, b = points[0], points[-1]
    for i in range(1, len(points) - 1):
        d = _point_line_dist(points[i], a, b)
        if d > dmax:
            dmax, index = d, i
    if dmax > epsilon:
        left = rdp(points[: index + 1], epsilon)
        right = rdp(points[index:], epsilon)
        return left[:-1] + right
    return [a, b]


def bbox(points: list[Point]) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) of a point set."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))
