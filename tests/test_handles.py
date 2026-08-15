from __future__ import annotations

import math

from mermaid2tm7.extract.handles import (
    perpendicular_offset,
    reduce_to_handle,
)


def test_fewer_than_three_points_returns_none():
    assert reduce_to_handle([(0, 0), (10, 0)]) is None
    assert reduce_to_handle([(0, 0)]) is None


def test_straight_line_returns_midpoint():
    pts = [(0, 0), (5, 0), (10, 0)]
    h = reduce_to_handle(pts, "max_deviation")
    assert h == (5, 0)


def test_max_deviation_picks_furthest_bend():
    pts = [(0, 0), (5, 8), (10, 0)]
    h = reduce_to_handle(pts, "max_deviation")
    assert h == (5, 8)


def test_arclength_mid():
    pts = [(0, 0), (10, 0), (20, 0)]
    h = reduce_to_handle(pts, "arclength_mid")
    assert math.isclose(h[0], 10, abs_tol=1e-6)
    assert math.isclose(h[1], 0, abs_tol=1e-6)


def test_bend_centroid():
    pts = [(0, 0), (4, 2), (6, 4), (10, 0)]
    h = reduce_to_handle(pts, "bend_centroid")
    assert math.isclose(h[0], 5, abs_tol=1e-6)
    assert math.isclose(h[1], 3, abs_tol=1e-6)


def test_perpendicular_offset_is_normal():
    ox, oy = perpendicular_offset((0, 0), (10, 0), 5.0)
    # chord is horizontal; normal is vertical
    assert math.isclose(ox, 0, abs_tol=1e-9)
    assert math.isclose(abs(oy), 5, abs_tol=1e-9)
