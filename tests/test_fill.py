"""
Tests for the fill-gap feature.

Intended to make sure the algorithms work correctly.
"""

import itertools
from datetime import UTC, datetime

import pytest

from gphix.fill import (
    Gap,
    ReferencePaths,
    RefPoint,
    fill_gaps,
    find_gaps,
    interpolate_time_fill,
    interpolate_time_linear,
)
from gphix.gpx import GPX

from .utils import Point, create_gpx


def test_find_gaps_basic():
    """Gaps detected between distant segments."""
    gpx = create_gpx(
        [Point(48.8584, 2.2945, time=0), Point(48.86, 2.3, time=10)],
        [Point(51.5074, -0.1278, time=3600), Point(51.51, -0.12, time=3610)],
    )
    (gap,) = find_gaps(gpx, min_distance=200.0)
    assert abs(gap.distance - 341_000) < 1000
    assert abs(gap.duration - 3600 + 10) < 0.1


def test_find_gaps_min_distance():
    """No gaps when segments are close."""
    gpx = create_gpx(
        [Point(48.8584, 2.2945, time=0), Point(48.8585, 2.2946, time=10)],
        [Point(48.8586, 2.2947, time=120), Point(48.8587, 2.2948, time=130)],
    )
    assert len(find_gaps(gpx, min_distance=200.0)) == 0
    assert len(find_gaps(gpx, min_distance=2.0)) == 1


def test_find_gaps_min_time():
    """Time threshold filtering."""
    gpx = create_gpx([Point(48.85, 2.29, time=0)], [Point(40.71, -74.06, time=0)])
    assert len(find_gaps(gpx, min_distance=200.0)) == 1
    assert len(find_gaps(gpx, min_distance=200.0, min_time=60.0)) == 0


def test_find_gaps_multiple_gaps():
    """Multiple gaps between multiple segments."""
    gpx = create_gpx(
        [Point(48.8, 2.2, time=0), Point(48.81, 2.21, time=10)],
        [Point(51.5, -0.1, time=3600), Point(51.51, -0.09, time=3610)],
        [Point(40.7, -74.0, time=7200), Point(40.71, -73.99, time=7210)],
        [Point(40.8, -73.0), Point(40.9, -73.0)],
    )
    gaps = find_gaps(gpx, min_distance=200.0)
    assert len(gaps) == 3


def test_find_gaps_single_track():
    """Single track → no gaps."""
    gpx = create_gpx([Point(48.8584, 2.2945), Point(48.86, 2.3)])
    assert find_gaps(gpx, min_distance=200.0) == []


@pytest.mark.parametrize(
    "start_dir,end_dir,reverse",
    [(s, e, d) for s in (-1, 0, 1) for e in (-1, 0, 1) for d in (False, True)],
    ids=[
        f"{s}_{e}_{d}"
        for s in ("before", "at", "after")
        for e in ("before", "at", "after")
        for d in ["forward", "reverse"]
    ],
)
def test_find_path(start_dir: int, end_dir: int, reverse: bool):
    """Test edge projection and path assembly in various configurations."""
    ref_pts = [
        Point(48.5, 2.5),
        Point(49.0, 2.0),
        Point(49.5, 1.5),
        Point(50.0, 1.0),
        Point(50.5, 0.5),
    ]
    start_pt = RefPoint(0, 49.0 + start_dir * 0.05, 2.0)
    end_pt = RefPoint(0, 50.0 + end_dir * 0.05, 1.0)
    if reverse:
        ref_pts = list(reversed(ref_pts))
    matcher = ReferencePaths(create_gpx(ref_pts))
    gap = Gap(start_pt, end_pt, 1e6)
    length = 3 + int(start_dir < 0) + int(end_dir > 0)
    path = matcher.find_path(gap)
    assert path is not None
    assert len(path) == length
    lats = [p.lat for p in path]
    assert lats == sorted(lats)


@pytest.mark.parametrize(
    "reverse,single",
    [(r, s) for r in (False, True) for s in (False, True)],
    ids=[f"{s}_{r}" for r in ("forward", "reverse") for s in ("multi", "single")],
)
def test_find_path_same_index(reverse: bool, single: bool):
    """Both gap endpoints map to the same index but project to different edges."""
    pts = [Point(0.0, 0.0), Point(10.0, 0.0), Point(10.1, 10.0)]
    if reverse:
        pts = reversed(pts)
    matcher = ReferencePaths(create_gpx(pts))
    if single:
        gap = Gap(RefPoint(0, 10.0, -2.0), RefPoint(0, 11.0, -0.5), 1e6)
    else:
        gap = Gap(RefPoint(0, 9.5, 0.0), RefPoint(0, 10.0, 0.5), 1e6)
    path = matcher.find_path(gap)
    assert path is not None
    assert len(path) == (1 if single else 3)
    assert path[len(path) // 2].lat == 10.0
    assert path[len(path) // 2].lon == 0.0
    lats = [p.lat for p in path]
    assert lats == sorted(lats)


def test_find_match_different_tracks():
    """Candidates on different tracks → no match."""
    r = create_gpx(
        (Point(48.8, 2.1), Point(48.7, 2.2)), (Point(51.5, 0.0), Point(51.6, 0.0))
    )
    g = create_gpx([Point(48.8, 2.2)], [Point(51.5, -0.1)])
    (gap,) = find_gaps(g)
    assert ReferencePaths(r).find_path(gap) is None


def test_find_path_distance_rejection():
    """Closest ref points too far from gap endpoints → None."""
    r = create_gpx([Point(48.8, 2.2), Point(48.81, 2.19), Point(48.82, 2.18)])
    matcher = ReferencePaths(r)
    # Gap endpoints are far from any ref points
    gap = Gap(RefPoint(-1, 0.0, 0.0), RefPoint(-1, 1.0, 1.0), 100.0)
    assert matcher.find_path(gap) is None


@pytest.mark.parametrize("second", [False, True], ids=("first", "second"))
def test_find_path_multi_segment(second: bool):
    """Multiple candidate segments; the best deviation is chosen."""
    r = create_gpx(
        [Point(47.5, 2.0), Point(48.0, 2.0), Point(48.5, 2.0), Point(49.0, 2.0)],
        [Point(47.5, 2.5), Point(48.0, 2.5), Point(48.5, 2.5), Point(49.0, 2.5)],
    )
    matcher = ReferencePaths(r)
    off = int(second) / 10
    gap = Gap(RefPoint(-1, 47.2, 2.1 + off), RefPoint(-1, 49.3, 2.3 + off), 1e6)
    path = matcher.find_path(gap)
    assert path is not None
    assert all(p.segment == int(second) for p in path)


def test_interpolate_linear():
    """Both times → linear interpolation."""
    start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    end_time = datetime(2024, 1, 1, 12, 4, 0, tzinfo=UTC)
    points = [
        RefPoint(-1, 48.8, 2.2),
        RefPoint(-1, 48.81, 2.19),
        RefPoint(-1, 48.82, 2.18),
    ]
    interpolate_time_linear(points, start_time, end_time)
    assert points[0].time == start_time
    assert points[2].time == end_time
    for t1, t2 in itertools.pairwise(points):
        assert t1.time < t2.time


def test_interpolate_fill():
    """Only start → backfill from start."""
    time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    points = [
        RefPoint(-1, 48.8, 2.2),
        RefPoint(-1, 48.81, 2.19),
        RefPoint(-1, 48.82, 2.18),
    ]
    interpolate_time_fill(points, time, None, 1.0)
    assert points[0].time == time
    for t1, t2 in itertools.pairwise(points):
        assert t1.time < t2.time
    assert points[1].time is not None
    interpolate_time_fill(points, None, time, 1.0)
    assert points[-1].time == time
    for t1, t2 in itertools.pairwise(points):
        assert t1.time < t2.time
    assert points[1].time is not None


def test_fill_gaps():
    gpx = create_gpx(
        [Point(48.0, 3.3)],
        [Point(48.8, 2.2, time=0), Point(48.86, 2.3, time=10)],
        [Point(50.0, 1.0, time=3600), Point(50.5, 0.5, time=3610)],
        [Point(52.0, -0.3)],
        [Point(53.0, 0.3)],
    )
    original_segments = len(list(gpx.segments()))
    original_points = len(list(gpx.points()))
    lats = (48.0, 48.5, 48.8, 48.86, 49.0, 49.5, 50.0, 50.5, 51.0, 51.5, 52.0, 53.0)
    lons = (3.3, 2.2, 2.2, 2.3, 2.0, 1.5, 1.0, 0.5, 0.0, -0.1, -0.3, 0.3)
    r = create_gpx([Point(x, y) for x, y in zip(lats, lons)])
    assert fill_gaps(gpx, r) == 4
    assert len(list(gpx.segments())) == original_segments + 4
    assert len(list(gpx.points())) > original_points


def test_fill_gap_no_match():
    """Returns False when no ref match."""
    gpx = create_gpx([Point(48.85, 2.29, time=0)], [Point(51.50, -0.12, time=360)])
    r = create_gpx([Point(-33.8, 151.2), Point(-33.9, 151.1), Point(-34.0, 151.0)])
    assert fill_gaps(gpx, r) == 0


def test_fill_gaps_partial():
    """Fill only selected gap indices."""
    gpx = create_gpx(
        [Point(48.85, 2.29, time=0), Point(48.9, 2.3, time=10)],
        [Point(51.6, -0.1, time=3600), Point(51.5, -0.2, time=3610)],
        [Point(40.7, -7.0, time=7200), Point(40.72, -73.99, time=7210)],
    )
    r = create_gpx(
        [
            Point(48.9, 2.3),
            Point(49.5, 1.5),
            Point(50.5, 0.5),
            Point(51.6, -0.1),
            Point(45.0, -5.0),
            Point(40.7, -7.0),
        ]
    )
    assert len(find_gaps(gpx, min_distance=200.0)) == 2
    assert fill_gaps(gpx, r, selected_gaps=[0]) == 1
    assert len(find_gaps(gpx, min_distance=200.0)) == 1
