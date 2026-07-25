import xml.etree.ElementTree as ET
from collections.abc import Iterator
from os import PathLike


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
