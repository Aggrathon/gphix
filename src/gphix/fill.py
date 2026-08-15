from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from gphix.gpx import GPX, GPXPoint
from gphix.utils import LocalKDTree, cum_distance, distance, project_to_edge


@dataclass(slots=True)
class FrozenSection:
    segment_index: int  # 0-based index into gpx.segments()
    start_idx: int  # first point in the frozen sequence
    end_idx: int  # first point after the frozen sequence
    gap: Gap


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

    start: RefPoint
    end: RefPoint
    distance: float
    duration: float | None = None

    @classmethod
    def between(cls, before: GPXPoint, after: GPXPoint) -> Gap:
        start = RefPoint.from_gpx_point(before)
        end = RefPoint.from_gpx_point(after)
        dur = None
        if start.time is not None and end.time is not None:
            dur = (end.time - start.time).total_seconds()
        return Gap(start, end, start.distance(end), dur)


def find_frozen(
    gpx: GPX,
    min_distance: float = 50.0,
    min_duration: float = 30.0,
    min_frozen: int = 3,
) -> list[FrozenSection]:
    """Find frozen sections in every segment."""
    sections: list[FrozenSection] = []
    for si, seg in enumerate(gpx.segments()):
        points = list(seg.points())
        frozen_start = 0
        for i in range(len(points) - 1):
            if not (
                points[i].latitude == points[i + 1].latitude
                and points[i].longitude == points[i + 1].longitude
            ):
                frozen_end = i + 1
                if frozen_end - frozen_start > min_frozen:
                    gap = Gap.between(points[frozen_start], points[frozen_end])
                    if gap.distance < min_distance:
                        continue
                    if gap.duration is not None and gap.duration < min_duration:
                        continue
                    sections.append(FrozenSection(si, frozen_start, frozen_end, gap))
                frozen_start = frozen_end
    return sections


def find_gaps(
    gpx: GPX, min_distance: float = 200.0, min_duration: float = -1
) -> list[Gap]:
    """Find gaps between consecutive segments."""
    gaps = []
    for seg_a, seg_b in pairwise(gpx.segments(True)):
        prev = seg_a.last_point()
        next = seg_b.first_point()
        if prev is None or next is None:
            continue
        gap = Gap.between(prev, next)
        if gap.distance < min_distance:
            continue
        if gap.duration is not None and gap.duration < min_duration:
            continue
        gaps.append(gap)
    return gaps


class ReferencePaths:
    """KDTree index over a reference GPX for gap boundary matching."""

    def __init__(self, ref: GPX | None, gap_dist_mult: float = 0.5):
        if ref is None:
            self._ref_pts = []
            self._tree = None
        else:
            self._ref_pts = [
                RefPoint.from_gpx_point(pt, i)
                for i, seg in enumerate(ref.segments(sorted=False, routes=True))
                for pt in seg.points()
            ]
            self._tree = LocalKDTree((pt.lat, pt.lon) for pt in self._ref_pts)
        self.mult = gap_dist_mult

    def _iter_segment(self, index: int) -> Iterator[int]:
        segment = self._ref_pts[index].segment
        for pt in range(index, len(self._ref_pts)):
            if self._ref_pts[pt].segment != segment:
                break
            yield pt
        for pt in range(index - 1, -1, -1):
            if self._ref_pts[pt].segment != segment:
                break
            yield pt

    def _project_nearest(self, idx: int, point: RefPoint) -> tuple[RefPoint, int]:
        """Return (projected_point, direction) for the closest edge near idx.

        direction: -1 = edge before idx, 0 = idx itself, +1 = edge after idx.
        """
        mid = self._ref_pts[idx]
        best_proj = mid
        best_dist = mid.distance(point)
        best_dir = 0
        pa = (mid.lat, mid.lon, mid.ele)
        pp = (point.lat, point.lon)
        for direction in (-1, 1):
            if 0 <= idx + direction < len(self._ref_pts):
                other = self._ref_pts[idx + direction]
                if other.segment == mid.segment:
                    pb = (other.lat, other.lon, other.ele)
                    proj_coords = project_to_edge(pa, pb, pp)
                    proj = RefPoint(mid.segment, *proj_coords)
                    d = proj.distance(point)
                    if d < best_dist:
                        best_dist, best_proj, best_dir = d, proj, direction
        return best_proj, best_dir

    def _closest_point_in_segment(self, i: int, pt: RefPoint) -> int:
        return min(self._iter_segment(i), key=lambda j: pt.distance(self._ref_pts[j]))

    def find_path(self, gap: Gap) -> list[RefPoint]:
        """Find matching path in the reference GPX."""
        if self._tree is None:
            return [gap.start, gap.end]
        start = self._tree.query(gap.start.lat, gap.start.lon)
        end = self._tree.query(gap.end.lat, gap.end.lon)
        proj_start, dir_start = self._project_nearest(start, gap.start)
        proj_end, dir_end = self._project_nearest(end, gap.end)
        dist_start = proj_start.distance(gap.start)
        dist_end = proj_end.distance(gap.end)

        if self._ref_pts[start].segment != self._ref_pts[end].segment:
            # Paths should be limited to the same segment
            new_start = self._closest_point_in_segment(end, gap.start)
            np_start, nd_start = self._project_nearest(new_start, gap.start)
            ndi_start = np_start.distance(gap.start)
            new_end = self._closest_point_in_segment(start, gap.end)
            np_end, nd_end = self._project_nearest(new_end, gap.end)
            ndi_end = np_end.distance(gap.end)
            if dist_start + ndi_end > dist_end + ndi_start:
                start, proj_start = new_start, np_start
                dir_start, dist_start = nd_start, ndi_start
            else:
                end, proj_end, dir_end, dist_end = new_end, np_end, nd_end, ndi_end

        if dist_start + dist_end > gap.distance * self.mult:
            return [gap.start, gap.end]

        if start == end:
            if dir_start == dir_end:
                if dir_start == 0:
                    return [gap.start, proj_start, gap.end]
                return [gap.start, proj_start, proj_end, gap.end]
            return [gap.start, proj_start, self._ref_pts[start], proj_end, gap.end]

        path = [gap.start, proj_start]
        if start < end:
            start += int(dir_start >= 0)
            end += int(dir_end > 0)
            path.extend(self._ref_pts[start:end])
        else:
            start += int(dir_start > 0)
            end += int(dir_end >= 0)
            path.extend(reversed(self._ref_pts[end:start]))
        path.append(proj_end)
        path.append(gap.end)
        return path


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
    if len(path) <= 2:
        return False
    if gap.duration is not None:
        interpolate_time_linear(path, gap.start.time, gap.end.time)  # type: ignore
    elif gap.start.time is not None or gap.end.time is not None:
        stats = gpx.stats(False)
        if stats.duration > 0 and stats.distance > 0:
            velocity = stats.distance / stats.duration
            interpolate_time_fill(path, gap.start.time, gap.end.time, velocity)
    gpx.add_track(*((pt.lat, pt.lon, pt.ele, pt.time) for pt in path[1:-1]))
    return True


def fill_gaps(
    gpx: GPX,
    ref: ReferencePaths | GPX | None,
    min_distance: float = 200.0,
    min_duration: float = -1.0,
    selected_gaps: list[int] | None = None,
) -> int:
    """Find all gaps and fill the selected ones. Returns the number of gaps filled."""
    gaps = find_gaps(gpx, min_distance, min_duration)
    if selected_gaps is not None:
        gaps = [gaps[i] for i in selected_gaps]
    filled = 0
    if gaps:
        matcher = ref if isinstance(ref, ReferencePaths) else ReferencePaths(ref)
        for gap in gaps:
            if fill_gap(gpx, matcher, gap):
                filled += 1
    return filled


def fix_frozen(
    gpx: GPX,
    ref: ReferencePaths | GPX | None = None,
    min_distance: float = 50.0,
    min_duration: float = 30.0,
    min_frozen: int = 3,
    selected_sections: list[int] | None = None,
) -> int:
    """Fix frozen sections by interpolating coordinates. Returns the count fixed."""
    sections = find_frozen(gpx, min_distance, min_duration, min_frozen)
    if selected_sections is not None:
        sections = [sections[i] for i in selected_sections]
    if sections:
        matcher = ref if isinstance(ref, ReferencePaths) else ReferencePaths(ref)
        segments = gpx.segments(sorted=False)
        for sec in sections:
            seg = segments[sec.segment_index]
            path = matcher.find_path(sec.gap)
            _interpolate_path(list(seg.points())[sec.start_idx : sec.end_idx + 1], path)
    return len(sections)


def _interpolate_path(points: list[GPXPoint], path: list[RefPoint]):
    """Interpolate coordinates along a path."""
    dists = list(cum_distance([(p.lat, p.lon, p.ele) for p in path]))
    total_dist = dists[-1] if dists else 1.0
    m = len(points)
    idx = 0
    for j in range(1, m - 1):
        target_dist = j / (m - 1) * total_dist
        while dists[idx + 1] < target_dist:
            idx += 1
        seg_dist = dists[idx + 1] - dists[idx]
        seg_t = (target_dist - dists[idx]) / seg_dist if seg_dist > 0 else 0
        p1, p2 = path[idx], path[idx + 1]
        points[j].latitude = p1.lat + seg_t * (p2.lat - p1.lat)
        points[j].longitude = p1.lon + seg_t * (p2.lon - p1.lon)
        if p1.ele is not None and p2.ele is not None:
            points[j].elevation = p1.ele + seg_t * (p2.ele - p1.ele)
        else:
            points[j].elevation = None
