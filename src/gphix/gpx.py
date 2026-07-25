import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
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


class GPXPoint:
    """Wrapper for a GPX point (trkpt, wpt, or rtept)."""

    def __init__(self, element: ET.Element, namespace: dict[str, str]):
        self._element = element
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
            ele = ET.SubElement(self._element, "ele")
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

    def __init__(self, file_source: str | PathLike):
        self.tree = ET.parse(file_source)
        self.root = self.tree.getroot()

        self.ns_uri = self.root.attrib.get("xmlns", "http://www.topografix.com/GPX/1/1")
        self.namespaces: dict[str, str] = {"gpx": self.ns_uri}

    def points(self) -> Iterator[GPXPoint]:
        """Generator yielding all points (trkpt, wpt, rtept) in the GPX file."""
        for tag in ["trkpt", "wpt", "rtept"]:
            for node in self.root.findall(f".//gpx:{tag}", self.namespaces):
                yield GPXPoint(node, self.namespaces)

    def write(self, output_path: str | PathLike) -> None:
        """Write the GPX to a file."""
        if self.ns_uri:
            ET.register_namespace("", self.ns_uri)
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
