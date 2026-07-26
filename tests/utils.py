from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from os import PathLike


@dataclass
class Point:
    lat: float
    lon: float
    ele: float | None = None
    time: float | None = None  # seconds offset from base_time


def create_gpx_file(
    gpx_path: PathLike,
    *tracks: Sequence[Point],
    waypoints: Sequence[Point] | None = None,
    base_time: datetime = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    metadata: str = "",
):
    """Create a minimal GPX track file for testing.

    Args:
        gpx_path: Output file path.
        *tracks: Zero or more sequences of :class:`Point`. Each sequence becomes
            a ``<trk><trkseg>``.  When no tracks are given, a single track with
            the default 3 coordinates is created.
        waypoints: Zero or more :class:`Point` objects, each becomes a ``<wpt>``.
        base_time: Base datetime used when converting ``Point.time`` (seconds
            offset) to ISO 8601 timestamps.
        metadata: Raw XML to insert inside a ``<metadata>`` element (empty = none).
    """
    defaults = [
        Point(48.8584, 2.2945),
        Point(51.5074, -0.1278),
        Point(40.7128, -74.006),
    ]
    if not tracks:
        tracks = (defaults,)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="GPhiX" xmlns="http://www.topografix.com/GPX/1/1">',
    ]
    if metadata:
        lines.append("  <metadata>")
        lines.append(metadata)
        lines.append("  </metadata>")

    if waypoints:
        for wp in waypoints:
            ele = f"<ele>{wp.ele}</ele>" if wp.ele is not None else ""
            lines.append(f'    <wpt lat="{wp.lat}" lon="{wp.lon}">{ele}</wpt>')

    for track in tracks:
        lines.append("  <trk>")
        lines.append("    <trkseg>")
        for pt in track:
            ele = f"<ele>{pt.ele}</ele>" if pt.ele is not None else ""
            if pt.time is not None:
                t = f"<time>{(base_time + timedelta(seconds=pt.time)).isoformat()}</time>"
            else:
                t = ""
            lines.append(f'      <trkpt lat="{pt.lat}" lon="{pt.lon}">{ele}{t}</trkpt>')
        lines.append("    </trkseg>")
        lines.append("  </trk>")

    lines.append("</gpx>")

    with open(gpx_path, "w") as f:
        f.write("\n".join(lines))
