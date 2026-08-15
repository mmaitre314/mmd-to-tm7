from __future__ import annotations

import math

import pytest

from mermaid2tm7.extract.paths import PathParseError, bbox, parse_path, rdp


def test_moveto_lineto():
    pts = parse_path("M0,0 L10,0 L10,10")
    assert pts == [(0, 0), (10, 0), (10, 10)]


def test_relative_lineto():
    pts = parse_path("M0,0 l5,0 l0,5")
    assert pts == [(0, 0), (5, 0), (5, 5)]


def test_horizontal_vertical():
    pts = parse_path("M0,0 H10 V10")
    assert pts == [(0, 0), (10, 0), (10, 10)]


def test_close_returns_to_start():
    pts = parse_path("M2,2 L8,2 L8,8 Z")
    assert pts[-1] == (2, 2)


def test_implicit_lineto_after_moveto():
    pts = parse_path("M0,0 1,1 2,2")
    assert pts == [(0, 0), (1, 1), (2, 2)]


def test_cubic_endpoints_preserved():
    pts = parse_path("M0,0 C0,10 10,10 10,0")
    assert pts[0] == (0, 0)
    assert math.isclose(pts[-1][0], 10, abs_tol=1e-6)
    assert math.isclose(pts[-1][1], 0, abs_tol=1e-6)


def test_cubic_flattening_tolerance():
    coarse = parse_path("M0,0 C0,10 10,10 10,0", flatten_tol=5.0)
    fine = parse_path("M0,0 C0,10 10,10 10,0", flatten_tol=0.1)
    assert len(fine) > len(coarse)


def test_arc_rejected_by_default():
    with pytest.raises(PathParseError):
        parse_path("M0,0 A5,5 0 0 1 10,0")


def test_arc_allowed_for_shapes():
    pts = parse_path("M0,0 A5,5 0 0 1 10,0", allow_arcs=True)
    assert math.isclose(pts[-1][0], 10, abs_tol=1e-6)
    assert math.isclose(pts[-1][1], 0, abs_tol=1e-6)
    assert len(pts) > 2


def test_rdp_collinear_reduces_to_endpoints():
    pts = [(0, 0), (1, 0), (2, 0), (3, 0)]
    assert rdp(pts, epsilon=0.5) == [(0, 0), (3, 0)]


def test_rdp_keeps_bend():
    pts = [(0, 0), (5, 5), (10, 0)]
    out = rdp(pts, epsilon=1.0)
    assert (5, 5) in out


def test_bbox():
    assert bbox([(1, 2), (5, -1), (3, 9)]) == (1, -1, 5, 9)


def test_unsupported_command():
    with pytest.raises(PathParseError):
        parse_path("M0,0 K1,1")
