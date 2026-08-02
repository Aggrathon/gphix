from __future__ import annotations

import itertools
import math
import tarfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from io import BytesIO
from os import PathLike
from typing import IO

from gphix.gpx import GPX, GPXPoint
from gphix.utils import LocalKDTree, haversine, project_to_edge

GEOSPATIAL_EXT = (".tif", ".tiff", ".img", ".jp2", ".ras", ".dat", ".hgt")
GPX_EXT = (".gpx",)
ZIP_EXT = (".zip",)
TAR_EXT = (".tar", ".gz", ".tgz", ".tar.bz2", ".tar.xz")


class DEMFile:
    _interpn: Callable | None = None

    def __init__(self, path: str | PathLike | IO[bytes]):
        import rasterio
        from rasterio.crs import CRS
        from rasterio.transform import rowcol
        from rasterio.warp import transform
        from rasterio.windows import Window

        self._transform = transform
        self._rowcol = rowcol
        self._window = Window.from_slices
        self.handle = rasterio.open(path)
        self.crs = CRS.from_epsg(4326)

    def close(self):
        self.handle.close()

    def elevation(self, latitude: float, longitude: float) -> float | None:
        height, width = self.handle.shape
        lon, lat = self._transform(self.crs, self.handle.crs, [longitude], [latitude])
        rowf, colf = self._rowcol(self.handle.transform, lon[0], lat[0], op=lambda v: v)
        row, col = int(rowf), int(colf)
        if 0 <= row < height and 0 <= col < width:
            rows = (max(row - 1, 0), min(row + 2, height))
            cols = (max(col - 1, 0), min(col + 2, width))
            dem = self.handle.read(1, window=self._window(rows, cols))
            if dem.size:
                if self.handle.nodata is not None:
                    dem[dem == self.handle.nodata] = math.nan
                if dem.size == 1:
                    return float(dem[0, 0])
                if self._interpn is None:
                    from scipy.interpolate import interpn

                    self._interpn = interpn
                elevation = self._interpn(
                    (range(*rows), range(*cols)),
                    dem[..., None],
                    [[rowf - 0.5, colf - 0.5]],
                    method="slinear",
                    bounds_error=False,
                    fill_value=None,
                )[0, 0]
                return float(elevation)


def open_elevation_sources(
    paths: Sequence[PathLike], extract: bool = False
) -> tuple[list[DEMFile], list[GPX]]:
    """Open elevation sources (expanding archives).

    Args:
        paths: List of paths to elevation files. Supports regular geospatial files
            (e.g. .tif, .hgt), GPX files, and archives (zip, tar) containing either type.
        extract: Required on platforms where archive:// URLs are not supported.

    Returns:
        Tuple of (rasterio DEM file handles and GPX:s). Callers are responsible for closing rasterio handles.
    """
    dems: list = []
    gpxs: list[GPX] = []
    for path in paths:
        path_str = str(path)
        pl = path_str.lower()
        if pl.endswith(GEOSPATIAL_EXT):
            dems.append(DEMFile(path))
        elif pl.endswith(GPX_EXT):
            gpxs.append(GPX(path))
        elif pl.endswith(ZIP_EXT):
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    nl = name.lower()
                    if nl.endswith(GPX_EXT):
                        gpxs.append(GPX(BytesIO(archive.read(name))))
                    elif nl.endswith(GEOSPATIAL_EXT):
                        if extract:
                            dems.append(DEMFile(BytesIO(archive.read(name))))
                        else:
                            dems.append(DEMFile(f"zip+file://{path_str}!{name}"))
        elif pl.endswith(TAR_EXT):
            with tarfile.open(path) as archive:
                for item in archive:
                    if not item.isfile():
                        continue
                    nl = item.name.lower()
                    if nl.endswith(GPX_EXT):
                        gpxs.append(GPX(archive.extractfile(item)))
                    elif nl.endswith(GEOSPATIAL_EXT):
                        if extract:
                            dems.append(DEMFile(archive.extractfile(item)))
                        else:
                            dems.append(DEMFile(f"tar+file://{path_str}!{item.name}"))
        else:
            dems.append(DEMFile(path))

    return dems, gpxs


class GPXInterpolator:
    """Builds a spatial index over GPX track edges for elevation lookups.

    All GPX files are merged into a single index. Each edge (pair of adjacent vertices
    with elevation) is indexed. The search finds the nearest edge (perpendicular
    distance) and interpolates the elevation.

    Args:
        gpxs: List of GPX objects or paths to GPX files.
        radius: Maximum perpendicular distance from a query point
                to a GPX track edge for the GPX to claim the elevation.
    """

    def __init__(self, gpxs: Sequence[GPX | PathLike], radius: float = 50.0):
        self.radius = radius
        self._chunks: list[Edge] = []
        self._tree = None

        edges = []
        for src in gpxs:
            gpx: GPX = src if isinstance(src, GPX) else GPX(src)
            for seg in gpx.segments(sorted=False, routes=True):
                for p1, p2 in itertools.pairwise(seg.points()):
                    if p1.elevation is not None and p2.elevation is not None:
                        edges.append(Edge.new(p1, p2))

        if not edges:
            return

        chunk_size = max(1.0, 2 * radius)
        pts: list[tuple[float, float]] = []
        for edge in edges:
            num_chunks = max(1, round(edge.length() / chunk_size))
            for i in range(num_chunks):
                pts.append(edge.lerp((i + 0.5) / num_chunks))
                self._chunks.append(edge)
        self._tree = LocalKDTree(pts)

    def elevation(self, latitude: float, longitude: float) -> float | None:
        """Return elevation from the closest GPX track edge, or ``None``."""
        if not self._chunks or self._tree is None:
            return None

        hits = self._tree.query_ball_point(
            latitude, longitude, r=max(1.0, 2 * self.radius)
        )
        best_dist = math.inf
        best_elev = None
        for chunk_idx in hits:
            edge = self._chunks[chunk_idx]
            perp_dist, elev = edge.closest(latitude, longitude)
            if perp_dist <= self.radius and perp_dist < best_dist:
                best_dist = perp_dist
                best_elev = elev
        return best_elev


@dataclass(slots=True)
class Edge:
    """A line segment between two GPX vertices with known elevations."""

    point1: tuple[float, float, float]
    point2: tuple[float, float, float]

    @classmethod
    def new(cls, p1: GPXPoint, p2: GPXPoint) -> Edge:
        return Edge(
            (p1.latitude, p1.longitude, p1.elevation),
            (p2.latitude, p2.longitude, p2.elevation),
        )

    def closest(self, lat: float, lon: float) -> tuple[float, float]:
        """Return (distance, elevation) of the closest point on the edge."""
        (lat2, lon2, ele2) = project_to_edge(self.point1, self.point2, (lat, lon))
        dist = haversine(lat2, lon2, lat, lon)
        return dist, ele2

    def length(self) -> float:
        return haversine(*self.point1[:-1], *self.point2[:-1])

    def lerp(self, t: float) -> tuple[float, float]:
        lat1, lon1, _ = self.point1
        lat2, lon2, _ = self.point2
        return lat1 + t * (lat2 - lat1), lon1 + t * (lon2 - lon1)


class ElevationDataManager:
    """Context manager for elevation sources (DEM files and GPX references).

    Args:
        paths: List of paths to elevation files. Supports regular geospatial files
            (e.g. .tif, .hgt), GPX files, and archives (zip, tar) containing either type.
        radius: Maximum perpendicular distance from a query point
                to a GPX track edge for the GPX to claim the elevation.
        extract: Required on platforms where archive:// URLs are not supported.
    """

    def __init__(
        self, paths: Sequence[PathLike], radius: float = 50.0, extract: bool = False
    ):
        self.paths = paths
        self.dem_files = []
        self.extract = extract
        self.radius = radius
        self.gpx_provider: GPXInterpolator | None = None

    def __enter__(self):
        self.dem_files, gpxs = open_elevation_sources(self.paths, self.extract)
        if gpxs:
            self.gpx_provider = GPXInterpolator(gpxs, self.radius)
        return self

    def elevation(self, latitude: float, longitude: float) -> float | None:
        """Query elevation for a point.

        GPX reference files are queried first; DEM is used as fallback.

        Args:
            latitude: Latitude of the point.
            longitude: Longitude of the point.

        Returns:
            Elevation in meters, or None if unavailable.
        """
        if self.gpx_provider:
            value = self.gpx_provider.elevation(latitude, longitude)
            if value is not None:
                return value

        for i, dem_file in enumerate(self.dem_files):
            elevation = dem_file.elevation(latitude, longitude)
            if elevation is not None:
                if i > 0:  # Move file to index 0 (likely used for next query)
                    self.dem_files.insert(0, self.dem_files.pop(i))
                if math.isnan(elevation):
                    return None
                return elevation
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        for dem_file in self.dem_files:
            dem_file.close()
        self.dem_files.clear()
        self.gpx_provider = None


def add_elevation_to_gpx(
    gpx: GPX,
    paths: Sequence[PathLike],
    overwrite: bool = False,
    extract: bool = False,
    radius: float = 50.0,
) -> int:
    """Add elevation data to a GPX file.

    Args:
        paths: List of paths to elevation files. Supports regular geospatial files
            (e.g. .tif, .hgt), GPX files, and archives (zip, tar) containing either type.
        overwrite: If True, overwrite existing elevation data.
        extract: Required on platforms where archive:// URLs are not supported.
        radius: Maximum perpendicular distance from a query point
                to a GPX track edge for the GPX to claim the elevation.

    Returns:
        The number of points with elevation updates.
    """
    point_updates = 0
    with ElevationDataManager(paths, radius, extract) as elevation:
        for point in gpx.points():
            if overwrite or point.elevation is None:
                value = elevation.elevation(point.latitude, point.longitude)
                if value is not None:
                    point.elevation = value
                    point_updates += 1
    return point_updates
