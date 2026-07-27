from __future__ import annotations

import copy
import itertools
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from os import PathLike

from .utils import distance, update_bounds


@dataclass
class GPXSegment:
    """A GPX track segment or route with its parent and point elements."""

    track: ET.Element
    segment: ET.Element
    uri: str
    namespaces: dict[str, str]
    point_tag: str = "trkpt"
    _time: datetime | bool | None = None

    @property
    def time(self) -> datetime | bool:
        """Timestamp of the first point in this segment, computed lazily and cached."""
        if self._time is None:
            if (pt := self.first_point()) and pt.time is not None:
                self._time = pt.time
            else:
                self._time = False
        return self._time

    def first_point(self) -> GPXPoint | None:
        """Return the first point in this segment, or None if empty."""
        if (
            pt := self.segment.find(f"gpx:{self.point_tag}", self.namespaces)
        ) is not None:
            return GPXPoint(pt, self.uri, self.namespaces)
        return None

    def __len__(self) -> int:
        """Number of points in this segment."""
        return len(self.segment.findall(f"gpx:{self.point_tag}", self.namespaces))

    def points(self) -> Iterator[GPXPoint]:
        """Yield `GPXPoint` for each point in this segment."""
        for pt in self.segment.findall(f"gpx:{self.point_tag}", self.namespaces):
            yield GPXPoint(pt, self.uri, self.namespaces)

    def remove(self, target: GPXPoint | None):
        """Remove a point (or the whole segment if None) from the track."""
        if target is None:
            self.track.remove(self.segment)
        else:
            self.segment.remove(target.element)


@dataclass(frozen=True)
class GPXStats:
    """Computed statistics for a GPX file."""

    points: int
    distance: float
    duration: float
    start_time: datetime | None
    end_time: datetime | None
    min_lat: float | None
    max_lat: float | None
    min_lon: float | None
    max_lon: float | None
    min_elev: float | None
    max_elev: float | None
    tracks: int


class TrackBuilder:
    """Builder for adding track segments and points."""

    def __init__(self, root: ET.Element, uri: str, namespaces: dict[str, str]):
        track = ET.SubElement(root, f"{{{uri}}}trk")
        self._segment = ET.SubElement(track, f"{{{uri}}}trkseg")
        self._namespaces = namespaces
        self._uri = uri

    def add_point(self, lat: float, lon: float, ele: float | None = None) -> GPXPoint:
        """Add a point to this track segment and return its wrapper."""
        pt = ET.SubElement(
            self._segment, f"{{{self._uri}}}trkpt", lat=str(lat), lon=str(lon)
        )
        point = GPXPoint(pt, self._uri, self._namespaces)
        if ele is not None:
            point.elevation = ele
        return point

    def add_points(self, *coords: tuple[float, float] | tuple[float, float, float]) -> TrackBuilder:
        """Call add_point multiple times."""
        for coord in coords:
            self.add_point(*coord)
        return self


@dataclass
class GPXPoint:
    """Wrapper for a GPX point (trkpt, wpt, or rtept)."""

    element: ET.Element
    uri: str
    namespace: dict[str, str]

    @property
    def latitude(self) -> float:
        return float(self.element.get("lat", ""))

    @property
    def longitude(self) -> float:
        return float(self.element.get("lon", ""))

    @property
    def elevation(self) -> float | None:
        ele = self.element.find("gpx:ele", self.namespace)
        return float(ele.text) if ele is not None and ele.text is not None else None

    @elevation.setter
    def elevation(self, value: float):
        ele = self.element.find("gpx:ele", self.namespace)
        if ele is None:
            ele = ET.SubElement(self.element, f"{{{self.uri}}}ele")
        ele.text = f"{value:.3g}"

    @property
    def time(self) -> datetime | None:
        """ISO 8601 time parsed as datetime, or None if absent."""
        t = self.element.find("gpx:time", self.namespace)
        if t is None or t.text is None:
            return None
        return datetime.fromisoformat(t.text)

    @time.setter
    def time(self, value: datetime):
        t = self.element.find("gpx:time", self.namespace)
        if t is None:
            t = ET.SubElement(self.element, f"{{{self.uri}}}time")
        t.text = value.isoformat()


class GPX:
    """Lightweight GPX parser."""

    def __init__(self, file_source: PathLike | BytesIO | None = None):
        self.uri = "http://www.topografix.com/GPX/1/1"
        if file_source is None:
            self.root = ET.Element(f"{{{self.uri}}}gpx", version="1.1", creator="GPhiX")
            self.tree = ET.ElementTree(self.root)
        else:
            self.tree = ET.parse(file_source)
            self.root = self.tree.getroot()
            self.uri = self.root.attrib.get("xmlns", self.uri)
        self.namespaces: dict[str, str] = {"gpx": self.uri}

    def add_track(self) -> TrackBuilder:
        """Add a track segment to the GPX and return a builder."""
        return TrackBuilder(self.root, self.uri, self.namespaces)

    def add_waypoint(self, lat: float, lon: float) -> GPXPoint:
        """Add a waypoint to the GPX and return its wrapper."""
        wpt = ET.SubElement(self.root, f"{{{self.uri}}}wpt", lat=str(lat), lon=str(lon))
        return GPXPoint(wpt, self.uri, self.namespaces)

    @classmethod
    def merge(cls, sources: list[GPX | PathLike | BytesIO]) -> GPX:
        """Merge multiple GPX files or objects into a single GPX object."""
        merged = cls(None)
        no_metadata = True
        for source in sources:
            src: GPX = source if isinstance(source, GPX) else GPX(source)
            for child in src.root:
                tag = child.tag.split("}")[-1]
                if tag == "metadata" and no_metadata:
                    merged.root.append(child)
                    no_metadata = False
                elif tag in {"trk", "wpt", "rte"}:
                    merged.root.append(copy.deepcopy(child))
        return merged

    def points(self) -> Iterator[GPXPoint]:
        """Generator yielding all points (trkpt, wpt, rtept) in the GPX file."""
        for tag in ["trkpt", "wpt", "rtept"]:
            for node in self.root.findall(f".//gpx:{tag}", self.namespaces):
                yield GPXPoint(node, self.uri, self.namespaces)

    def to_string(self) -> str:
        """Serialize the GPX to an XML string."""
        buf = BytesIO()
        self.write(buf)
        return buf.getvalue().decode("utf-8")

    def write(self, output_path: PathLike | BytesIO) -> None:
        """Write the GPX to a file."""
        if self.uri:
            ET.register_namespace("", self.uri)
        self.tree.write(output_path, encoding="utf-8", xml_declaration=True)

    def stats(self) -> GPXStats:
        """Compute and return statistics for all points in the GPX."""
        duration = 0.0
        length = 0.0
        points = 0
        bounds_time = None, None
        bounds_elev = None, None
        bounds_lat = None, None
        bounds_lon = None, None
        for seg in self.segments(sort=False, routes=True):
            times = []
            lats = []
            lons = []
            elev = []
            for p in seg.points():
                if p.time:
                    times.append(p.time)
                lats.append(p.latitude)
                lons.append(p.longitude)
                elev.append(p.elevation)
            points += len(lats)
            if times:
                start = max(times)
                end = min(times)
                duration += (start - end).total_seconds()
                bounds_time = update_bounds(*bounds_time, (start, end))
            if lats:
                length += distance(zip(lats, lons, elev))
                bounds_lat = update_bounds(*bounds_lat, lats)
                bounds_lon = update_bounds(*bounds_lon, lons)
                bounds_elev = update_bounds(
                    *bounds_elev, [e for e in elev if e is not None]
                )

        track_count = len(self.root.findall("gpx:trk", self.namespaces))

        return GPXStats(
            points=points,
            distance=length,
            duration=duration,
            start_time=bounds_time[0],
            end_time=bounds_time[1],
            min_lat=bounds_lat[0],
            max_lat=bounds_lat[1],
            min_lon=bounds_lon[0],
            max_lon=bounds_lon[1],
            min_elev=bounds_elev[0],
            max_elev=bounds_elev[1],
            tracks=track_count,
        )

    def segments(self, sort: bool = True, routes: bool = False) -> list[GPXSegment]:
        """Return ``GPXSegment`` objects.

        Args:
            sort: Sort segments temporally (segments without timestamps first).
            routes: Also include route segments (``rte`` elements).
        """
        segments: list[GPXSegment] = []
        for trk in self.root.findall("gpx:trk", self.namespaces):
            for seg in trk.findall("gpx:trkseg", self.namespaces):
                segments.append(GPXSegment(trk, seg, self.uri, self.namespaces))

        if routes:
            for rte in self.root.findall("gpx:rte", self.namespaces):
                segments.append(
                    GPXSegment(self.root, rte, self.uri, self.namespaces, "rtept")
                )

        if sort:
            with_time = sorted([s for s in segments if s.time], key=lambda s: s.time)
            without_time = [s for s in segments if not s.time]
            return without_time + with_time
        return segments

    def trim(
        self,
        start: float = 0.0,
        end: float = 0.0,
        by_time: bool = False,
        by_distance: bool = False,
    ) -> GPX:
        """Trim points from the start and end of all tracks.

        Tracks are sorted temporally (by earliest timestamp).
        Only points falling inside the middle are retained.

        Args:
            start:     Fraction (0.0–1.0) to remove from the beginning.
            end:       Fraction (0.0–1.0) to remove from the end.
            by_time:       If True, *start*/*end* are seconds.
            by_distance:   If True, *start*/*end* are metres.
                           Otherwise they are fractions of total points (0.0–1.0).

        Returns:
            A new `GPX` with the trimmed data (original is unchanged).
        """
        if by_time and by_distance:
            raise ValueError("Cannot specify both by_time and by_distance")

        clone = copy.deepcopy(self)
        segments = clone.segments()

        if not segments:
            return clone

        counter: float | int = 0.0
        if by_time:
            step = _step_time
        elif by_distance:
            step = _step_dist
        else:
            counter = -1
            step = lambda p1, p2: 1

        positions: list[tuple[GPXSegment, GPXPoint, float | int]] = []
        for seg in segments:
            first = seg.first_point()
            if first is not None:
                if not by_time and not by_distance:
                    counter += 1
                positions.append((seg, first, counter))
            for p1, p2 in itertools.pairwise(seg.points()):
                counter += step(p1, p2)
                positions.append((seg, p2, counter))

        if counter == 0:
            return clone

        if not by_time and not by_distance:
            start = round(start * (counter + 1))
            end = round(end * counter)

        if start + end >= counter:
            raise ValueError("Cannot remove more points than available")
        end = counter - end
        for seg, pt, pos in positions:
            if not (start <= pos <= end):
                seg.remove(pt)

        return clone


def _step_time(p1: GPXPoint, p2: GPXPoint) -> float | int:
    if (t1 := p1.time) is not None and (t2 := p2.time) is not None:
        return (t2 - t1).total_seconds()
    else:
        return 0.0


def _step_dist(p1: GPXPoint, p2: GPXPoint) -> float | int:
    return distance(
        (
            (p1.latitude, p1.longitude, p1.elevation),
            (p2.latitude, p2.longitude, p2.elevation),
        )
    )
