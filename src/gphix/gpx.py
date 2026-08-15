from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO, StringIO
from os import PathLike

from .utils import distance, last, update_bounds

PointTuple = (
    tuple[float, float]
    | tuple[float, float, float | None]
    | tuple[float, float, float | None, datetime | None]
)


@dataclass(slots=True)
class GPXSegment:
    """A GPX track segment or route with its parent and point elements."""

    parent: ET.Element
    element: ET.Element
    uri: str
    namespaces: dict[str, str]
    point_tag: str = "trkpt"

    def add_point(
        self,
        lat: float,
        lon: float,
        ele: float | None = None,
        time: datetime | None = None,
    ) -> GPXPoint:
        """Add a point to this segment and return its wrapper."""
        pt = ET.SubElement(
            self.element, f"{{{self.uri}}}{self.point_tag}", lat=str(lat), lon=str(lon)
        )
        point = GPXPoint(pt, self.uri, self.namespaces)
        if ele is not None:
            point.elevation = ele
        if time is not None:
            point.time = time
        return point

    def add_points(self, *coords: PointTuple):
        """Add points to this segment."""
        for coord in coords:
            self.add_point(*coord)

    def first_point(self) -> GPXPoint | None:
        """Return the first point in this segment, or None if empty."""
        pt = self.element.find(f"gpx:{self.point_tag}", self.namespaces)
        if pt is not None:
            return GPXPoint(pt, self.uri, self.namespaces)
        return None

    def last_point(self) -> GPXPoint | None:
        """Return the last point in this segment, or None if empty."""
        pt = last(self.element.iterfind(f"gpx:{self.point_tag}", self.namespaces))
        if pt is not None:
            return GPXPoint(pt, self.uri, self.namespaces)
        return None

    def points(self) -> Iterator[GPXPoint]:
        """Yield `GPXPoint` for each point in this segment."""
        for pt in self.element.iterfind(f"gpx:{self.point_tag}", self.namespaces):
            yield GPXPoint(pt, self.uri, self.namespaces)

    def remove(self, target: GPXPoint | None):
        """Remove a point (or the whole segment if None) from the track."""
        if target is None:
            self.parent.remove(self.element)
        else:
            self.element.remove(target.element)

    def __len__(self) -> int:
        return len(self.element)


@dataclass(slots=True)
class GPXMetadata:
    """Parsed metadata from a GPX file."""

    name: str | None = None
    description: str | None = None
    author: str | None = None
    email: str | None = None
    copyright: str | None = None
    links: tuple[tuple[str, str, str | None], ...] = ()
    time: datetime | None = None
    keywords: str | None = None
    min_lat: float | None = None
    max_lat: float | None = None
    min_lon: float | None = None
    max_lon: float | None = None

    def to_string(self) -> str:
        """Return metadata as XML."""
        meta = ET.Element("metadata")
        self._to_xml(meta, "")
        return ET.tostring(meta).decode("utf-8")

    def _to_xml(self, root: ET.Element, ns: str):
        """Append metadata XML elements to `root` using namespace `ns`."""

        def elem(parent: ET.Element, tag: str, text: str | None):
            if text:
                ET.SubElement(parent, f"{ns}{tag}").text = text

        elem(root, "name", self.name)
        elem(root, "desc", self.description)
        if self.author is not None or self.email is not None:
            author = ET.SubElement(root, f"{ns}author")
            elem(author, "name", self.author)
            elem(author, "email", self.email)
        elem(root, "copyright", self.copyright)
        for href, text, link_type in self.links:
            link = ET.SubElement(root, f"{ns}link", href=href)
            elem(link, "text", text)
            elem(link, "type", link_type)
        if self.time is not None:
            elem(root, "time", self.time.isoformat())
        elem(root, "keywords", self.keywords)
        bounds_attrs = {
            attr: str(val)
            for attr, val in (
                ("minlat", self.min_lat),
                ("maxlat", self.max_lat),
                ("minlon", self.min_lon),
                ("maxlon", self.max_lon),
            )
            if val is not None
        }
        if bounds_attrs:
            ET.SubElement(root, f"{ns}bounds", bounds_attrs)


@dataclass(frozen=True, slots=True)
class GPXStats:
    """Computed statistics for a GPX file."""

    points: int
    distance: float
    duration: float
    start_time: datetime | None
    end_time: datetime | None
    min_elev: float | None
    max_elev: float | None
    tracks: int


@dataclass(slots=True)
class GPXTrack:
    """Wrapper for a GPX track (<trk>) element with metadata and segment support."""

    element: ET.Element
    uri: str
    namespaces: dict[str, str]

    def _get(self, tag: str) -> str | None:
        el = self.element.find(f"gpx:{tag}", self.namespaces)
        return el.text if el is not None else None

    def _set(self, tag: str, value: str | None):
        el = self.element.find(f"gpx:{tag}", self.namespaces)
        if not value:
            if el is not None:
                self.element.remove(el)
        else:
            if el is None:
                el = ET.SubElement(self.element, f"{{{self.uri}}}{tag}")
            el.text = value

    @property
    def name(self) -> str | None:
        return self._get("name")

    @name.setter
    def name(self, value: str | None) -> None:
        self._set("name", value)

    @property
    def description(self) -> str | None:
        return self._get("desc")

    @description.setter
    def description(self, value: str | None) -> None:
        self._set("desc", value)

    @property
    def track_type(self) -> str | None:
        return self._get("type")

    @track_type.setter
    def track_type(self, value: str | None) -> None:
        self._set("type", value)

    def add_segment(self, *coords: PointTuple) -> GPXSegment:
        """Create a new <trkseg> with optional points and return it."""
        seg = ET.SubElement(self.element, f"{{{self.uri}}}trkseg")
        result = GPXSegment(self.element, seg, self.uri, self.namespaces)
        if coords:
            result.add_points(*coords)
        return result


@dataclass(slots=True)
class GPXPoint:
    """Wrapper for a GPX point (trkpt, wpt, or rtept)."""

    element: ET.Element
    uri: str
    namespaces: dict[str, str]

    def _get(self, tag: str) -> str | None:
        el = self.element.find(f"gpx:{tag}", self.namespaces)
        return el.text if el is not None else None

    def _set(self, tag: str, text: str | None) -> None:
        el = self.element.find(f"gpx:{tag}", self.namespaces)
        if text is None:
            if el is not None:
                self.element.remove(el)
            return
        if el is None:
            el = ET.SubElement(self.element, f"{{{self.uri}}}{tag}")
        el.text = text

    @property
    def latitude(self) -> float:
        return float(self.element.get("lat", ""))

    @latitude.setter
    def latitude(self, value: float) -> None:
        self.element.set("lat", f"{value:.6g}")

    @property
    def longitude(self) -> float:
        return float(self.element.get("lon", ""))

    @longitude.setter
    def longitude(self, value: float) -> None:
        self.element.set("lon", f"{value:.6g}")

    @property
    def elevation(self) -> float | None:
        ele = self._get("ele")
        return float(ele) if ele else None

    @elevation.setter
    def elevation(self, value: float | None) -> None:
        self._set("ele", f"{value:.5g}" if value is not None else None)

    @property
    def time(self) -> datetime | None:
        """ISO 8601 time parsed as datetime, or None if absent."""
        t = self._get("time")
        return datetime.fromisoformat(t) if t else None

    @time.setter
    def time(self, value: datetime) -> None:
        self._set("time", value.isoformat())

    def __bool__(self) -> bool:
        return True


class GPX:
    """Lightweight GPX parser."""

    def __init__(self, file_source: PathLike | str | BytesIO | StringIO | None = None):
        self.uri = "http://www.topografix.com/GPX/1/1"
        if file_source is None:
            self.root = ET.Element(f"{{{self.uri}}}gpx", version="1.1", creator="GPhiX")
            self.tree = ET.ElementTree(self.root)
        else:
            self.tree = ET.parse(file_source)
            self.root = self.tree.getroot()
            self.uri = self.root.attrib.get("xmlns", self.uri)
        self.namespaces: dict[str, str] = {"gpx": self.uri}

    def add_track(
        self,
        *coords: PointTuple,
        name: str | None = None,
        description: str | None = None,
        track_type: str | None = None,
    ) -> GPXTrack:
        """Add a track to the GPX and return its wrapper.

        Args:
            *coords: Optional points in a new segment.
            name: Track name.
            description: Track description.
            track_type: Track type.
        """
        el = ET.SubElement(self.root, f"{{{self.uri}}}trk")
        track = GPXTrack(el, self.uri, self.namespaces)
        if name is not None:
            track.name = name
        if description is not None:
            track.description = description
        if track_type is not None:
            track.track_type = track_type
        if coords:
            track.add_segment(*coords)
        return track

    def tracks(self) -> list[GPXTrack]:
        """Return ``GPXTrack`` wrappers for all tracks in document order."""
        return [
            GPXTrack(trk, self.uri, self.namespaces)
            for trk in self.root.iterfind("gpx:trk", self.namespaces)
        ]

    def add_waypoint(self, lat: float, lon: float) -> GPXPoint:
        """Add a waypoint to the GPX and return its wrapper."""
        wpt = ET.SubElement(self.root, f"{{{self.uri}}}wpt", lat=str(lat), lon=str(lon))
        return GPXPoint(wpt, self.uri, self.namespaces)

    @classmethod
    def merge(cls, sources: list[GPX | PathLike | BytesIO]) -> GPX:
        """Merge multiple GPX files or objects into a single GPX object."""
        first = sources[0]
        merged: GPX = copy.deepcopy(first) if isinstance(first, GPX) else GPX(first)
        for source in sources[1:]:
            src: GPX = source if isinstance(source, GPX) else GPX(source)
            for child in src.root:
                tag = child.tag.split("}")[-1]
                if tag in {"trk", "wpt", "rte"}:
                    merged.root.append(copy.deepcopy(child))
        return merged

    def points(self) -> Iterator[GPXPoint]:
        """Generator yielding all points (trkpt, wpt, rtept) in the GPX file."""
        for tag in ["trkpt", "wpt", "rtept"]:
            for node in self.root.iterfind(f".//gpx:{tag}", self.namespaces):
                yield GPXPoint(node, self.uri, self.namespaces)

    def waypoints(self) -> Iterator[GPXPoint]:
        """Generator yielding all points (trkpt, wpt, rtept) in the GPX file."""
        for node in self.root.iterfind(".//gpx:wpt", self.namespaces):
            yield GPXPoint(node, self.uri, self.namespaces)

    def metadata(self) -> GPXMetadata | None:
        """Return parsed metadata from the GPX file, or None if absent."""
        meta = self.root.find("gpx:metadata", self.namespaces)
        if meta is None:
            return None

        def text(tag: str, parent: ET.Element) -> str | None:
            el = parent.find(f"gpx:{tag}", self.namespaces)
            return el.text if el is not None and el.text else None

        author_name = author_email = None
        if (author := meta.find("gpx:author", self.namespaces)) is not None:
            author_name = text("name", author)
            author_email = text("email", author)

        links = []
        for link in meta.iterfind("gpx:link", self.namespaces):
            if href := link.get("href"):
                link_text = text("text", link) or link.text
                link_type = text("type", link)
                links.append((href, link_text or "", link_type))

        min_lat = max_lat = min_lon = max_lon = None
        if (bounds := meta.find("gpx:bounds", self.namespaces)) is not None:
            min_lat = float(v) if (v := bounds.get("minlat")) else None
            max_lat = float(v) if (v := bounds.get("maxlat")) else None
            min_lon = float(v) if (v := bounds.get("minlon")) else None
            max_lon = float(v) if (v := bounds.get("maxlon")) else None
        time = text("time", meta)

        return GPXMetadata(
            name=text("name", meta),
            description=text("desc", meta),
            author=author_name,
            email=author_email,
            copyright=text("copyright", meta),
            links=tuple(links),
            time=datetime.fromisoformat(time) if time else None,
            keywords=text("keywords", meta),
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
        )

    def set_metadata(self, metadata: GPXMetadata):
        """Set metadata. If the GPX file already contains metadata, it is replaced.

        Args:
            metadata: The metadata to write.
        """
        meta = self.root.find("gpx:metadata", self.namespaces)
        if meta is None:
            meta = ET.SubElement(self.root, f"{{{self.uri}}}metadata")
        else:
            meta.clear()
        metadata._to_xml(meta, f"{{{self.uri}}}")

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

    def stats(self, count_routes: bool = True) -> GPXStats:
        """Compute and return statistics for all points in the GPX."""
        duration = 0.0
        length = 0.0
        points = 0
        bounds_time = None, None
        bounds_elev = None, None
        for seg in self.segments(sorted=False, routes=count_routes):
            times = []
            coords = []
            for p in seg.points():
                if p.time:
                    times.append(p.time)
                coords.append((p.latitude, p.longitude, p.elevation))
            points += len(coords)
            if times:
                start = max(times)
                end = min(times)
                duration += (start - end).total_seconds()
                bounds_time = update_bounds(*bounds_time, (start, end))
            if coords:
                length += distance(coords)
                bounds_elev = update_bounds(
                    *bounds_elev, [e for _, _, e in coords if e is not None]
                )
        track_count = len(self.root.findall("gpx:trk", self.namespaces))

        return GPXStats(
            points=points,
            distance=length,
            duration=duration,
            start_time=bounds_time[0],
            end_time=bounds_time[1],
            min_elev=bounds_elev[0],
            max_elev=bounds_elev[1],
            tracks=track_count,
        )

    def segments(self, sorted: bool = False, routes: bool = False) -> list[GPXSegment]:
        """Return `GPXSegment` objects.

        Args:
            sort: Sort segments temporally, bridging gaps with time-less
                segments by geographic proximity.
            routes: Also include route segments (`rte` elements).
        """
        out = []
        timed = []
        untimed = []
        for trk in self.root.iterfind("gpx:trk", self.namespaces):
            for seg in trk.iterfind("gpx:trkseg", self.namespaces):
                segment = GPXSegment(trk, seg, self.uri, self.namespaces)
                if first := segment.first_point():
                    if not sorted:
                        out.append(segment)
                    elif time := first.time:
                        timed.append((time, first, segment))
                    else:
                        untimed.append((first, segment))

        if routes:
            for rte in self.root.iterfind("gpx:rte", self.namespaces):
                segment = GPXSegment(self.root, rte, self.uri, self.namespaces, "rtept")
                if first := segment.first_point():
                    if not sorted:
                        out.append(segment)
                    elif time := first.time:
                        timed.append((time, first, segment))
                    else:
                        untimed.append((first, segment))

        if len(timed) + len(untimed) == 0:
            return out

        if not timed:
            return [seg for _, seg in untimed]
        timed.sort(key=lambda x: x[0])
        if not untimed:
            return [seg for _, _, seg in timed]

        fixed = [
            (
                (first.latitude, first.longitude, first.elevation),
                (last.latitude, last.longitude, last.elevation),
                segment,
            )
            for _, first, segment in timed
            if (last := segment.last_point())
        ]
        for first, segment in untimed:
            last = segment.last_point() or first

            sf = (first.latitude, first.longitude, first.elevation)
            sl = (last.latitude, last.longitude, last.elevation)
            best_cost, best_idx = float("inf"), 0

            if not fixed:
                fixed.append((sf, sl, segment))
                continue
            for i in range(len(fixed) + 1):
                if i == 0:
                    cost = distance((sl, fixed[0][0])) * 2
                elif i == len(fixed):
                    cost = distance((fixed[-1][1], sf)) * 2
                else:
                    cost = distance((fixed[i - 1][1], sf)) + distance((sl, fixed[i][0]))
                if cost < best_cost:
                    best_cost, best_idx = cost, i
            fixed.insert(best_idx, (sf, sl, segment))
        return [seg for *_, seg in fixed]

    def clean(
        self,
        outliers: bool = False,
        max_distance: float = 100.0,
        max_time: float = float("inf"),
        min_size: int = 1,
        merge_tracks: bool = False,
        add_bounds: bool = False,
    ):
        """Remove empty segments, tracks, outliers, and refresh metadata.

        Args:
            outliers: Remove consecutive points farther than *max_distance*.
            max_distance: Threshold in metres for outlier removal.
            max_time: Threshold in seconds for outlier removal.
            min_size: Remove segments shorter than this.
            merge_tracks: Merge all tracks into a single track.
            add_bounds: Create metadata time and coordinate bounds if not existing.
        """
        if outliers:
            self._remove_outliers(max_distance, max_time)

        for trk in self.root.iterfind("gpx:trk", self.namespaces):
            for seg in trk.iterfind("gpx:trkseg", self.namespaces):
                if len(seg) < min_size:
                    trk.remove(seg)
            if len(trk) == 0:
                self.root.remove(trk)
        for rte in self.root.iterfind("gpx:rte", self.namespaces):
            if len(rte) == 0:
                self.root.remove(rte)

        if merge_tracks:
            track_count = len(self.root.findall("gpx:trk", self.namespaces))
            if track_count >= 2:
                segments = self.segments(sorted=True, routes=False)
                merged = copy.deepcopy(self.root.find("gpx:trk", self.namespaces))
                assert merged is not None
                for seg in merged.findall("gpx:trkseg", self.namespaces):
                    merged.remove(seg)
                for seg in segments:
                    merged.append(copy.deepcopy(seg.element))
                for trk in self.root.findall("gpx:trk", self.namespaces):
                    self.root.remove(trk)
                self.root.append(merged)

        meta = self.metadata()
        if add_bounds and meta is None:
            meta = GPXMetadata()
        if meta is not None:
            add_time = add_bounds or meta.time is not None
            add_bounds = add_bounds or meta.min_lat is not None
            if add_bounds:
                meta.min_lat = float("inf")
                meta.min_lon = float("inf")
                meta.max_lat = -float("inf")
                meta.max_lon = -float("inf")
            if add_time:
                orig_time = datetime.max.replace(tzinfo=UTC)
                meta.time = orig_time
            if add_bounds or add_time:
                for pt in self.points():
                    if add_time and (time := pt.time) is not None:
                        meta.time = min(meta.time, time)
                    if add_bounds:
                        lat, lon = pt.latitude, pt.longitude
                        meta.min_lat = min(meta.min_lat, lat)
                        meta.max_lat = max(meta.max_lat, lat)
                        meta.min_lon = min(meta.min_lon, lon)
                        meta.max_lon = max(meta.max_lon, lon)
                if add_time and meta.time == orig_time:
                    meta.time = None
            self.set_metadata(meta)

    def _remove_outliers(self, max_distance: float, max_time: float) -> None:
        """Remove consecutive points whose distance exceeds *max_distance*."""
        for seg in self.segments(False, False):
            length = len(seg)
            max_out = 1 + int(length > 10) + int(length > 100) + int(length > 1000)
            if length <= max_out + 1:
                continue
            to_remove = []
            path = []
            lp, lt = (0, 0, 0), None
            for pt in seg.points():
                p, t = (pt.latitude, pt.longitude, pt.elevation), pt.time
                if not path:
                    path = [pt]
                elif (distance((lp, p)) < max_distance) and (
                    (t is None) or (lt is None) or ((t - lt).total_seconds() < max_time)
                ):
                    path.append(pt)
                else:
                    if len(path) <= max_out:
                        to_remove.extend(path)
                    path = [pt]
                lp, lt = p, t
            if len(path) <= max_out:
                to_remove.extend(path)
            if len(to_remove) <= length / 4:
                for pt in to_remove:
                    seg.remove(pt)
