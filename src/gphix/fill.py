from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from gphix.gpx import GPX, GPXPoint
from gphix.utils import LocalKDTree, cum_distance, distance


@dataclass(slots=True)
class RefPoint:
    segment: int
    lat: float
    lon: float
    ele: float | None = None
    time: datetime | None = None

    @classmethod
    def from_gpx_point(cls, point: GPXPoint, segment: int = -1) -> RefPoint:
        return RefPoint(
            segment, point.latitude, point.longitude, point.elevation, point.time
        )

    def distance(self, other: RefPoint) -> float:
        return distance(
            ((self.lat, self.lon, self.ele), (other.lat, other.lon, other.ele))
        )


@dataclass(slots=True)
class Gap:
    """A gap between two track segments in a GPX."""

    start_point: RefPoint
    end_point: RefPoint
    distance: float
    start_time: datetime | None = None
    end_time: datetime | None = None


def find_gaps(
    gpx: GPX, min_distance: float = 200.0, min_time: float | None = None
) -> list[Gap]:
    """Find gaps between consecutive segments."""
    gaps = []
    for seg_a, seg_b in pairwise(gpx.segments()):
        prev = seg_a.last_point()
        next = seg_b.first_point()
        if prev is None or next is None:
            continue
        start = RefPoint.from_gpx_point(prev)
        end = RefPoint.from_gpx_point(next)
        dist = start.distance(end)
        if dist < min_distance:
            continue
        if start.time is not None and end.time is not None:
            gap_time = (end.time - start.time).total_seconds()
            if min_time is not None and gap_time < min_time:
                continue
        gaps.append(
            Gap(
                start_point=start,
                end_point=end,
                distance=dist,
                start_time=start.time,
                end_time=end.time,
            )
        )
    return gaps


class ReferencePaths:
    """KDTree index over a reference GPX for gap boundary matching."""

    def __init__(self, ref: GPX):
        self._tree = LocalKDTree(
            (pt.latitude, pt.longitude)
            for seg in ref.segments(sorted=False, routes=True)
            for pt in seg.points()
        )
        self._ref_pts = [
            RefPoint.from_gpx_point(pt, i)
            for i, seg in enumerate(ref.segments(sorted=False, routes=True))
            for pt in seg.points()
        ]

    def find_path(self, gap: Gap) -> list[RefPoint] | None:
        """Find matching path in the reference GPX."""
        start = self._tree.query(gap.start_point.lat, gap.start_point.lon)
        end = self._tree.query(gap.end_point.lat, gap.end_point.lon)
        spoint = self._ref_pts[start]
        epoint = self._ref_pts[end]
        if self._ref_pts[start].segment != self._ref_pts[end].segment:
            # Different segments
            # TODO: find closest points in segments and choose better path
            return None
        # TODO find the closest edge and create the closes point as start and end
        sdist = spoint.distance(gap.start_point)
        edist = epoint.distance(gap.end_point)
        if sdist + edist > gap.distance:
            return None
        if start == end:
            return [self._ref_pts[start]]
        if start < end:
            return self._ref_pts[start : end + 1]
        else:
            return list(reversed(self._ref_pts[end : start + 1]))


def interpolate_time_linear(points: list[RefPoint], start: datetime, end: datetime):
    if points:
        dist = list(cum_distance((p.lat, p.lon, p.ele) for p in points))
        time = (end - start).total_seconds() / (dist[-1] or 1.0)
        for d, p in zip(dist, points):
            p.time = start + timedelta(seconds=time * d)


def interpolate_time_fill(
    points: list[RefPoint],
    start_time: datetime | None,
    end_time: datetime | None,
    velocity: float,
):
    dist = list(cum_distance((p.lat, p.lon, p.ele) for p in points))
    if start_time is not None:
        for d, p in zip(dist, points):
            p.time = start_time + timedelta(seconds=d / velocity)
    elif end_time is not None:
        off = dist[-1]
        for d, p in zip(dist, points):
            p.time = end_time + timedelta(seconds=(d - off) / velocity)
    else:
        raise ValueError("Must specify either start or end time.")


def fill_gap(gpx: GPX, matcher: ReferencePaths, gap: Gap) -> bool:
    """Fill a single gap (uses a pre-built matcher)."""
    path = matcher.find_path(gap)
    if path is None:
        return False
    builder = gpx.add_track()
    if gap.start_time is not None and gap.end_time is not None:
        interpolate_time_linear(path, gap.start_time, gap.end_time)
    elif gap.start_time is not None or gap.end_time is not None:
        stats = gpx.stats(False)
        if stats.duration > 0 and stats.distance > 0:
            velocity = stats.distance / stats.duration
            interpolate_time_fill(path, gap.start_time, gap.end_time, velocity)
    for pt in path:
        p = builder.add_point(pt.lat, pt.lon, pt.ele)
        if pt.time is not None:
            p.time = pt.time
    return True


def fill_gaps(
    gpx: GPX,
    ref: GPX,
    min_distance: float = 200.0,
    min_time: float | None = None,
    selected_gaps: list[int] | None = None,
) -> int:
    """Find all gaps and fill the selected ones. Returns the number of gaps filled."""
    gaps = find_gaps(gpx, min_distance, min_time)
    if selected_gaps is not None:
        gaps = [gaps[i] for i in selected_gaps]
    filled = 0
    if gaps:
        matcher = ReferencePaths(ref)
    for gap in gaps:
        if fill_gap(gpx, matcher, gap):
            filled += 1
    return filled
