"""
Tests for the fill-gap feature.

Intended to make sure the algorithms work correctly.
"""

import itertools
from datetime import UTC, datetime

import pytest

from gphix.fix import (
    Gap,
    ReferencePaths,
    RefPoint,
    fill_gaps,
    find_frozen,
    find_gaps,
    fix_frozen,
    interpolate_time,
)

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
    assert len(find_gaps(gpx, min_distance=200.0, min_duration=60.0)) == 0


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
    assert len(path) == length + 2
    lats = [p.lat for p in path[1:-1]]
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
    assert len(path) == (3 if single else 5)
    assert path[len(path) // 2].lat == 10.0
    assert path[len(path) // 2].lon == 0.0
    lats = [p.lat for p in path[1:-1]]
    assert lats == sorted(lats)


def test_find_match_different_tracks():
    """Candidates on different tracks → no match."""
    r = create_gpx(
        (Point(48.8, 2.1), Point(48.7, 2.2)), (Point(51.5, 0.0), Point(51.6, 0.0))
    )
    g = create_gpx([Point(48.8, 2.2)], [Point(51.5, -0.1)])
    (gap,) = find_gaps(g)
    assert len(ReferencePaths(r, 0.5).find_path(gap)) == 2
    assert len(ReferencePaths(r, 1.0).find_path(gap)) == 2
    assert len(ReferencePaths(r, 2.0).find_path(gap)) == 5


def test_find_path_distance_rejection():
    """Closest ref points too far from gap endpoints → None."""
    r = create_gpx([Point(48.8, 2.2), Point(48.81, 2.19), Point(48.82, 2.18)])
    matcher = ReferencePaths(r)
    # Gap endpoints are far from any ref points
    gap = Gap(RefPoint(-1, 0.0, 0.0), RefPoint(-1, 1.0, 1.0), 100.0)
    assert len(matcher.find_path(gap)) == 2


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
    assert all(p.segment == int(second) for p in path[1:-1])


@pytest.mark.parametrize(
    "start,end",
    [(s, e) for s in (True, False) for e in (True, False) if e or s],
    ids=["both", "start", "end"],
)
def test_interpolate_linear(start: bool, end: bool):
    """Both times → linear interpolation."""
    start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    end_time = datetime(2024, 1, 1, 12, 4, 0, tzinfo=UTC)
    points = [
        RefPoint(-1, 48.8, 2.2),
        RefPoint(-1, 48.81, 2.19),
        RefPoint(-1, 48.82, 2.18),
    ]
    dist = points[0].distance(points[1]) + points[1].distance(points[2])
    time = (end_time - start_time).total_seconds()
    interpolate_time(
        points,
        start_time if start else None,
        end_time if end else None,
        dist / time if not start or not end else None,
    )
    assert points[0].time == start_time
    assert points[2].time == end_time
    for t1, t2 in itertools.pairwise(points):
        assert t1.time < t2.time


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


def _create_frozen(lat: float, lon: float, offset: float = 0.1) -> list[Point]:
    off = [Point(lat + offset, lon + offset, time=50)]
    return [Point(lat, lon, time=i * 10) for i in range(5)] + off


def test_find_frozen_basic():
    """Single frozen zone detected."""
    gpx = create_gpx(_create_frozen(45.3, -23.2, 0.001))
    (zone,) = find_frozen(gpx, min_duration=30.0, min_distance=50.0, min_frozen=3)
    assert zone.segment_index == 0
    assert zone.start_idx == 0
    assert zone.end_idx == 5
    assert zone.gap.distance > 50
    assert zone.gap.duration is not None and zone.gap.duration >= 30
    assert find_frozen(gpx, min_duration=30.0, min_distance=50.0, min_frozen=5) == []
    assert find_frozen(gpx, min_duration=300.0, min_distance=50.0, min_frozen=3) == []
    assert find_frozen(gpx, min_duration=30.0, min_distance=500.0, min_frozen=3) == []


def test_find_frozen_no_freeze():
    """All points moving -> no frozen zones."""
    gpx = create_gpx([Point(41.0, 29.0 + i * 0.1, time=i * 10) for i in range(10)])
    assert find_frozen(gpx) == []


def test_find_frozen_multiple_segments():
    """Zones in multiple segments."""
    gpx = create_gpx(_create_frozen(-54.4, 44.4), _create_frozen(45.5, -55.5))
    zones = find_frozen(gpx)
    assert len(zones) == 2
    assert zones[0].segment_index == 0
    assert zones[1].segment_index == 1
    assert zones[0].gap.distance > 50
    assert zones[1].gap.distance > 50


def test_find_frozen_trailing_freeze():
    """Trailing frozen run at end of segment -> not emitted."""
    gpx = create_gpx(list(reversed(_create_frozen(4.2, 2.4))))
    assert find_frozen(gpx) == []


def test_find_frozen_multiple_zones():
    """Two separate frozen zones in one segment."""
    gpx = create_gpx(_create_frozen(-3.2, 7.4) + _create_frozen(3.1, -7.5))
    zones = find_frozen(gpx)
    assert len(zones) == 2
    assert zones[0].start_idx == 0
    assert zones[0].end_idx == 5
    assert zones[1].start_idx == 6
    assert zones[1].end_idx == 11
    assert zones[0].gap.distance > 50
    assert zones[1].gap.distance > 50


def test_find_frozen_no_timestamps():
    """No time data -> duration=None passes."""
    gpx = create_gpx(
        [
            Point(41.2, 29.4),
            Point(41.2, 29.4),
            Point(41.2, 29.4),
            Point(41.2, 29.4),
            Point(41.3, 29.5),
        ]
    )
    zones = find_frozen(gpx)
    assert len(zones) == 1
    assert zones[0].gap.duration is None


def test_fix_frozen_basic():
    """Single zone fixed with reference."""
    gpx = create_gpx(_create_frozen(43.2, 22.4))
    original_times = [p.time for p in gpx.points()]
    r = create_gpx(
        [Point(42.2, 22.4), Point(42.21, 22.42), Point(42.25, 22.46), Point(42.3, 22.5)]
    )
    fixed = fix_frozen(gpx, r)
    assert fixed == 1

    seg = gpx.segments(sorted=False)[0]
    pts = list(seg.points())
    assert pts[0].latitude == pytest.approx(43.2)
    assert pts[-1].latitude == pytest.approx(43.3)
    for i in range(1, 5):
        assert pts[i - 1].latitude < pts[i].latitude
        assert pts[i - 1].longitude < pts[i].longitude
    for j, pt in enumerate(pts):
        assert pt.time == original_times[j]
    assert len(list(gpx.segments())) == 1
    assert len(list(gpx.points())) == len(original_times)
    assert find_frozen(gpx) == []


def test_fix_frozen_multiple_zones():
    """Multiple zones both fixed."""
    gpx = create_gpx(_create_frozen(41.2, 29.4) + _create_frozen(41.4, 29.6))
    r = create_gpx([Point(41.2 + i * 0.01, 29.4 + i * 0.01, i) for i in range(20)])
    fixed = fix_frozen(gpx, r)
    assert fixed == 2
    assert find_frozen(gpx) == []
    for p1, p2 in itertools.pairwise(gpx.points()):
        e1, e2 = p1.elevation, p2.elevation
        assert e1 is None or e2 is None or e1 < e2


@pytest.mark.parametrize("ref", [None, [Point(-33.8, 151.2), Point(-33.9, 151.1)]])
def test_fix_frozen_linear_fallback(ref):
    """No reference or no match -> linear interpolation."""
    gpx = create_gpx(_create_frozen(67.3, 123.3))
    r = create_gpx(ref) if ref is not None else None
    fixed = fix_frozen(gpx, r)
    assert fixed == 1
    seg = gpx.segments(sorted=False)[0]
    pts = list(seg.points())
    for i in range(1, 5):
        assert pts[i - 1].latitude < pts[i].latitude
        assert pts[i - 1].longitude < pts[i].longitude
    assert find_frozen(gpx) == []
