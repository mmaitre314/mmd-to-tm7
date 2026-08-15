from __future__ import annotations

import math

import pytest

from mermaid2tm7.extract.transforms import Affine, parse_transform


def test_identity():
    a = Affine.identity()
    assert a.apply(3, 4) == (3, 4)


def test_translate():
    a = parse_transform("translate(10, 20)")
    assert a.apply(1, 2) == (11, 22)


def test_translate_single_arg():
    a = parse_transform("translate(5)")
    assert a.apply(0, 0) == (5, 0)


def test_scale():
    a = parse_transform("scale(2, 3)")
    assert a.apply(4, 5) == (8, 15)


def test_matrix():
    a = parse_transform("matrix(1 0 0 1 7 8)")
    assert a.apply(0, 0) == (7, 8)


def test_composition_order():
    # translate then scale: leftmost is outermost
    a = parse_transform("translate(10,0) scale(2)")
    # point (1,0): scale -> (2,0), translate -> (12,0)
    assert a.apply(1, 0) == (12, 0)


def test_rotate_90():
    a = parse_transform("rotate(90)")
    x, y = a.apply(1, 0)
    assert math.isclose(x, 0, abs_tol=1e-9)
    assert math.isclose(y, 1, abs_tol=1e-9)


def test_matmul_associative_with_apply():
    t = Affine.translate(5, 5)
    s = Affine.scale(2)
    composed = t @ s
    # apply s first, then t
    assert composed.apply(1, 1) == (7, 7)


def test_empty_transform_is_identity():
    assert parse_transform(None).apply(9, 9) == (9, 9)
    assert parse_transform("").apply(9, 9) == (9, 9)


@pytest.mark.parametrize("sep", ["translate(1,2)", "translate(1 2)", "translate( 1 , 2 )"])
def test_separator_variants(sep):
    assert parse_transform(sep).apply(0, 0) == (1, 2)
