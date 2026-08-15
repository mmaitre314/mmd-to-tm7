"""Reduce a flattened edge polyline to a single TM7 curve handle.

Implements ``docs/03-svg-extraction-spec.md`` §Handle point reduction. TM7 stores
one ``HandleX/HandleY`` per data flow, so the whole routed polyline must collapse
to one point.

Spike A5 (choosing between strategies against TMT's actual rendering) requires
the Windows Threat Modeling Tool and is not runnable in this environment. Until it
is run, the default is ``max_deviation``: the interior point furthest from the
straight source->target chord. It degrades gracefully to the chord midpoint for
near-straight edges and best represents a single-bend route, which is the common
case. See ``docs/investigation.md``.
"""

from __future__ import annotations

import math

Point = tuple[float, float]

Strategy = str  # "arclength_mid" | "max_deviation" | "bend_centroid"

DEFAULT_STRATEGY: Strategy = "max_deviation"


def _dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _chord_midpoint(points: list[Point]) -> Point:
    a, b = points[0], points[-1]
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _arclength_mid(points: list[Point]) -> Point:
    total = sum(_dist(points[i], points[i + 1]) for i in range(len(points) - 1))
    if total == 0.0:
        return points[0]
    half = total / 2.0
    acc = 0.0
    for i in range(len(points) - 1):
        seg = _dist(points[i], points[i + 1])
        if acc + seg >= half:
            t = (half - acc) / seg if seg else 0.0
            return (
                points[i][0] + t * (points[i + 1][0] - points[i][0]),
                points[i][1] + t * (points[i + 1][1] - points[i][1]),
            )
        acc += seg
    return points[-1]


def _point_line_dist(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    seg2 = dx * dx + dy * dy
    if seg2 == 0.0:
        return _dist(p, a)
    return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / math.sqrt(seg2)


def _max_deviation(points: list[Point]) -> Point:
    a, b = points[0], points[-1]
    best, best_d = points[len(points) // 2], -1.0
    for p in points[1:-1]:
        d = _point_line_dist(p, a, b)
        if d > best_d:
            best_d, best = d, p
    if best_d <= 0.5:  # essentially straight
        return _chord_midpoint(points)
    return best


def _bend_centroid(points: list[Point]) -> Point:
    interior = points[1:-1]
    if not interior:
        return _chord_midpoint(points)
    return (
        sum(p[0] for p in interior) / len(interior),
        sum(p[1] for p in interior) / len(interior),
    )


def reduce_to_handle(
    points: list[Point], strategy: Strategy = DEFAULT_STRATEGY
) -> Point | None:
    """Reduce a flattened edge polyline to a single TM7 curve handle.

    Returns ``None`` for degenerate paths (fewer than 3 points); the mapper then
    writes a straight flow using the chord midpoint.
    """
    if len(points) < 3:
        return None
    if strategy == "arclength_mid":
        return _arclength_mid(points)
    if strategy == "bend_centroid":
        return _bend_centroid(points)
    if strategy == "max_deviation":
        return _max_deviation(points)
    raise ValueError(f"unknown handle strategy: {strategy!r}")


def perpendicular_offset(a: Point, b: Point, magnitude: float) -> Point:
    """Unit-normal * magnitude for the chord a->b, used to separate parallel edges."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    return (-dy / length * magnitude, dx / length * magnitude)
