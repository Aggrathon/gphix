from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from os import PathLike

import numpy as np
import pytest

from gphix.gpx import GPX, GPXMetadata, GPXPoint


@dataclass(slots=True)
class Point:
    lat: float
    lon: float
    ele: float | None = None
    time: float | None = None

    def date(self, time: datetime) -> None | datetime:
        return (time + timedelta(seconds=self.time)) if self.time is not None else None


def create_gpx(
    *tracks: Sequence[Point],
    waypoints: Sequence[Point] | None = None,
    base_time: datetime = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    metadata: GPXMetadata | None = None,
) -> GPX:
    """Create a minimal GPX for testing.

    Args:
        *tracks: Zero or more sequences of `Point`. Each sequence becomes a
            `<trk><trkseg>`. When no tracks are given, a single track with
            the default 3 coordinates is created.
        waypoints: Zero or more `Point` objects, each becomes a ``<wpt>``.
        base_time: Base datetime used when converting ``Point.time`` (seconds
            offset) to ISO 8601 timestamps.
        metadata: ``GPXMetadata`` instance to serialize (``None`` = none).
    """
    default = [Point(-48.8, 2.2), Point(51.4, -0.8), Point(40.1, -74.6)]
    gpx = GPX(None)
    for track in tracks or (default,):
        gpx.add_track(*((p.lat, p.lon, p.ele, p.date(base_time)) for p in track))
    for wpt in waypoints or ():
        if wpt.ele is None:
            gpx.add_waypoint(wpt.lat, wpt.lon)
        else:
            gpx.add_waypoint(wpt.lat, wpt.lon).elevation = wpt.ele
    if metadata:
        gpx.set_metadata(metadata)
    return gpx


def create_gpx_file(
    gpx_path: PathLike,
    *tracks: Sequence[Point],
    waypoints: Sequence[Point] | None = None,
    base_time: datetime = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    metadata: GPXMetadata | None = None,
):
    """Create a minimal GPX track file for testing.

    Args:
        gpx_path: Output file path.
        *tracks: Zero or more sequences of `Point`. Each sequence becomes
            a ``<trk><trkseg>``.  When no tracks are given, a single track with
            the default 3 coordinates is created.
        waypoints: Zero or more `Point` objects, each becomes a ``<wpt>``.
        base_time: Base datetime used when converting ``Point.time`` (seconds
            offset) to ISO 8601 timestamps.
        metadata: ``GPXMetadata`` instance to serialize.
    """
    default = [Point(48.8584, 2.2945), Point(51.5074, -0.1278), Point(40.7128, -74.006)]

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="GPhiX_test" xmlns="http://www.topografix.com/GPX/1/1">',
    ]
    if metadata:
        lines.append(metadata.to_string())

    if waypoints:
        for wp in waypoints:
            ele = f"<ele>{wp.ele}</ele>" if wp.ele is not None else ""
            lines.append(f'    <wpt lat="{wp.lat}" lon="{wp.lon}">{ele}</wpt>')

    for track in tracks or (default,):
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


def create_tif_point(path, latitude: float, longitude: float, elevation: float = 0.0):
    grid = np.full((1, 1), elevation, dtype=np.float32)
    create_tif_grid(
        path, longitude - 0.01, latitude - 0.01, longitude + 0.01, latitude + 0.01, grid
    )


def create_tif_grid(
    path,
    west: float,
    south: float,
    east: float,
    north: float,
    elevations: np.ndarray | float,
):
    import rasterio
    from rasterio.transform import from_bounds

    if np.isscalar(elevations):
        elevations = np.full((3, 3), elevations, dtype=np.float32)
    height, width = elevations.shape
    transform = from_bounds(west, south, east, north, width, height)
    with rasterio.open(
        str(path),
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=elevations.dtype,
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999,
    ) as dst:
        dst.write(elevations, 1)


def no_np_warn():
    return pytest.mark.filterwarnings("ignore:Setting the shape:DeprecationWarning")


def assert_same_points(a: Iterable[GPXPoint], b: Iterable[GPXPoint]):
    for pa, pb in zip(a, b, strict=True):
        assert pa.latitude == pb.latitude
        assert pa.longitude == pb.longitude
        assert pa.elevation == pb.elevation
        assert pa.time == pb.time
