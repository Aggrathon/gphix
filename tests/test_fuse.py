"""Tests for the fuse module (DTW offset estimation and attribute fusion)."""

import pytest

from gphix.fuse import fuse_segments, suggest_offset
from gphix.gpx import GPX

from .utils import Point, create_gpx


@pytest.mark.parametrize("time_shift", [-15, 0, 15])
@pytest.mark.parametrize("drift", [0.667, 1.0, 2.0])
@pytest.mark.parametrize("num_diff", [-10, 10])
@pytest.mark.parametrize("index", [-2, 2])
def test_suggest_offset(time_shift, drift, num_diff, index):
    num_base = 20
    num_src = num_base + num_diff
    base = create_gpx([Point(-3.0 + i * 0.01, 8.2, time=i) for i in range(num_base)])
    source = create_gpx(
        [
            Point(-3.0 + i * 0.01 * drift, 8.2, time=i * drift + time_shift)
            for i in range(index, num_src + index)
        ]
    )
    offset, residual = suggest_offset(base, source)
    if drift == int(drift) or abs(num_base - num_src * drift) < 0.01:
        assert offset == pytest.approx(time_shift, abs=0.001)
        assert residual == pytest.approx(0.0, abs=0.001)
    else:
        assert offset == pytest.approx(time_shift, abs=0.3)
        assert residual > 0


def test_suggest_offset_no_segments():
    empty = GPX(None)
    source = create_gpx([Point(48.8, 2.2, time=i) for i in range(10)])
    with pytest.raises(ValueError, match="segment"):
        suggest_offset(empty, source)


@pytest.mark.parametrize("ele", [None, 50])
@pytest.mark.parametrize("offset", [0, 20])
@pytest.mark.parametrize("max_time", [5, 30])
@pytest.mark.parametrize("shift", [-2, 2])
def test_fuse_segments(ele, offset, max_time, shift):
    base = create_gpx(
        [
            Point(4.8 + i * 0.01, 2.2, time=i * 100, ele=ele + i if ele else None)
            for i in range(10)
        ]
    )
    source = create_gpx(
        [
            Point(4.8 + i * 0.01, 2.2, ele=100.0 + i, time=i * 100 + 20)
            for i in range(shift, 10 + shift)
        ]
    )
    pts, attrs = fuse_segments(base, source, offset=offset, max_time=max_time)

    matched = 20 - offset < max_time
    assert pts == (8 if matched else 0)
    assert attrs == 0 if ele or not matched else 8
    for i, pt in enumerate(base.points()):
        if ele is None and (not matched or i < shift or i > 9 + shift):
            assert pt.elevation is None
        else:
            assert pt.elevation == pytest.approx((ele or 100) + i, abs=0.1)


def test_fuse_segments_multiple_sources():
    base = create_gpx([Point(48.8 + i * 0.01, 2.2, time=i) for i in range(10)])
    source1 = create_gpx(
        [Point(48.8 + i * 0.01, 2.2, ele=100.0 + i, time=i) for i in range(10)]
    )
    source2 = create_gpx([Point(48.8 + i * 0.01, 2.2, time=i) for i in range(10)])

    # Set a custom attribute on source2 (hr)
    for pt in source2.segments()[0].points():
        pt.element.append(pt.element.makeelement("gpx_xi:hr", {"gpx_xi:href": ""}))
        pt.element[-1].text = "150"

    pts, attrs = fuse_segments(base, source1)
    assert pts == 10
    assert attrs == 10
    pts, attrs = fuse_segments(base, source2)
    assert pts == 10
    assert attrs == 10
    for i, pt in enumerate(base.points()):
        assert pt.elevation == pytest.approx(100.0 + i, abs=0.1)
        assert pt.element[-1].text == "150"
