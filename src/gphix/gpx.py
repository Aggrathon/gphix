from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from os import PathLike

from .utils import distance


@dataclass(frozen=True)
class GPXStats:
    """Computed statistics for a GPX file."""

    points: int
    distance_m: float
    duration_s: float | None
    start_time: datetime | None
    end_time: datetime | None
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    min_elev: float | None
    max_elev: float | None


class TrackBuilder:
    """Builder for adding track segments and points."""

    def __init__(self, root: ET.Element, uri: str, namespaces: dict[str, str]):
        track = ET.SubElement(root, f"{{{uri}}}trk")
        self._segment = ET.SubElement(track, f"{{{uri}}}trkseg")
        self._namespaces = namespaces
        self._uri = uri

    def add_point(self, lat: float, lon: float) -> GPXPoint:
        """Add a point to this track segment and return its wrapper."""
        pt = ET.SubElement(
            self._segment, f"{{{self._uri}}}trkpt", lat=str(lat), lon=str(lon)
        )
        return GPXPoint(pt, self._uri, self._namespaces)

    def add_points(self, coords: Iterable[tuple[float, float]]) -> TrackBuilder:
        for lat, lon in coords:
            self.add_point(lat, lon)
        return self


class GPXPoint:
    """Wrapper for a GPX point (trkpt, wpt, or rtept)."""

    def __init__(self, element: ET.Element, uri: str, namespace: dict[str, str]):
        self._element = element
        self._uri = uri
        self._namespace = namespace

    @property
    def latitude(self) -> float:
        return float(self._element.get("lat", ""))

    @property
    def longitude(self) -> float:
        return float(self._element.get("lon", ""))

    @property
    def elevation(self) -> float | None:
        ele = self._element.find("gpx:ele", self._namespace)
        return float(ele.text) if ele is not None and ele.text is not None else None

    @elevation.setter
    def elevation(self, value: float):
        ele = self._element.find("gpx:ele", self._namespace)
        if ele is None:
            ele = ET.SubElement(self._element, f"{{{self._uri}}}ele")
        ele.text = f"{value:.3g}"

    @property
    def time(self) -> datetime | None:
        """ISO 8601 time parsed as datetime, or None if absent."""
        t = self._element.find("gpx:time", self._namespace)
        if t is None or t.text is None:
            return None
        return datetime.fromisoformat(t.text)


class GPX:
    """Lightweight GPX parser."""

    def __init__(self, file_source: PathLike | None = None):
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
    def merge(cls, sources: list[GPX | PathLike]) -> GPX:
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
        lats = []
        lons = []
        elev = []
        time = []
        for p in self.points():
            lats.append(p.latitude)
            lons.append(p.longitude)
            elev.append(p.elevation)
            if (tm := p.time) is not None:
                time.append(tm)
        total_distance = distance(zip(lats, lons, elev))
        elev = [e for e in elev if e is not None]

        if time:
            duration_s = (time[-1] - time[0]).total_seconds()
            start_time, end_time = time[0], time[-1]
        else:
            duration_s = start_time = end_time = None

        return GPXStats(
            points=len(lats),
            distance_m=total_distance,
            duration_s=duration_s,
            start_time=start_time,
            end_time=end_time,
            min_lat=min(lats, default=0.0),
            max_lat=max(lats, default=0.0),
            min_lon=min(lons, default=0.0),
            max_lon=max(lons, default=0.0),
            min_elev=min(elev, default=None),
            max_elev=max(elev, default=None),
        )
