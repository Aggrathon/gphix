import math
import os
import shutil
import tarfile
import tempfile
import zipfile
from collections.abc import Sequence
from os import PathLike

from gphix.gpx import GPX


class Lazy:
    """Static class for lazily loading heavy packages."""

    @classmethod
    def load(cls):
        """Make sure rasterio and scipy are imported."""
        import rasterio
        from rasterio.crs import CRS
        from rasterio.transform import rowcol
        from rasterio.warp import transform
        from rasterio.windows import Window
        from scipy.interpolate import interpn

        cls.open = rasterio.open
        cls.CRS = CRS
        cls.rowcol = rowcol
        cls.transform = transform
        cls.Window = Window
        cls.interpn = interpn


def open_dem_files(
    paths: Sequence[PathLike], extract: bool = False
) -> tuple[list, list[str]]:
    """Open DEM files, expanding archives and extracting archive items if needed.

    Args:
        paths: List of paths to DEM files. Supports regular geospatial files
               (e.g., .tif, .hgt, .img) and archives (zip, tar) containing
               geospatial files.
        extract: If True, force extract archive contents to temporary
                 directories before opening. Required on platforms where
                 archive:// URLs are not supported.

    Returns:
        Tuple of (list of opened rasterio DEM file handles, list of temp
        directory paths that were created for extracted files). Callers are
        responsible for closing file handles and cleaning up temp directories.
    """
    Lazy.load()

    dem_files: list = []
    temp_dirs: list[str] = []
    geospatial_ext = (".tif", ".tiff", ".img", ".jp2", ".ras", ".dat", ".hgt")
    for path in paths:
        path_str = str(path)
        path_lower = path_str.lower()

        if path_lower.endswith(geospatial_ext):
            dem_file = Lazy.open(path)
            dem_files.append(dem_file)
            continue

        if _try_open_zip(path_str, geospatial_ext, extract, dem_files, temp_dirs):
            continue

        if _try_open_tar(path_str, geospatial_ext, extract, dem_files, temp_dirs):
            continue

        dem_file = Lazy.open(path_str)
        dem_files.append(dem_file)

    return dem_files, temp_dirs


def _try_open_zip(
    path_str: str,
    geospatial_ext: tuple[str, ...],
    extract: bool,
    dem_files: list,
    temp_dirs: list[str],
) -> bool:
    """Try to open *path_str* as a ZIP archive.

    Returns ``True`` if the file is a valid ZIP (regardless of whether it
    contained geospatial items), ``False`` otherwise.
    """
    try:
        with zipfile.ZipFile(path_str) as archive:
            items = [
                item
                for item in archive.namelist()
                if item.lower().endswith(geospatial_ext)
            ]
            if items:
                if extract:
                    tmpdir = tempfile.mkdtemp()
                    temp_dirs.append(tmpdir)
                    for item in items:
                        dem_file = Lazy.open(archive.extract(item, tmpdir))
                        dem_files.append(dem_file)
                else:
                    for item in items:
                        dem_file = Lazy.open(f"zip+file://{path_str}!{item}")
                        dem_files.append(dem_file)
            return True
    except (zipfile.BadZipFile, OSError):
        return False


def _try_open_tar(
    path_str: str,
    geospatial_ext: tuple[str, ...],
    extract: bool,
    dem_files: list,
    temp_dirs: list[str],
) -> bool:
    """Try to open *path_str* as a tar archive.

    Returns ``True`` if the file is a valid tar, ``False`` otherwise.
    """
    try:
        with tarfile.open(path_str) as archive:
            items = [
                item
                for item in archive.getnames()
                if item.lower().endswith(geospatial_ext)
            ]
            if items:
                if extract:
                    tmpdir = tempfile.mkdtemp()
                    temp_dirs.append(tmpdir)
                    for item in items:
                        archive.extract(item, tmpdir, filter="data")
                        dem_file = Lazy.open(os.path.join(tmpdir, item))
                        dem_files.append(dem_file)
                else:
                    for item in items:
                        dem_file = Lazy.open(f"tar+file://{path_str}!{item}")
                        dem_files.append(dem_file)
            return True
    except (tarfile.TarError, OSError):
        return False


class ElevationDataManager:
    """Context manager for DEM files to simplify elevation queries.

    Args:
        dem_paths: List of paths to DEM files.
                Supports both regular files and zip/tar archives with multiple files.
                Also supports archive:// URLs (e.g., zip:///path/to/file.zip!dataset.tif).
        extract: If True, force extract archive contents before processing (on platforms where archive:// URLs are not working).
        verbose: If True, print information about the data source.
    """

    def __init__(self, dem_paths: Sequence[PathLike], extract: bool = False):
        Lazy.load()

        self.dem_paths = dem_paths
        self.dem_files: list = []
        self.temp_dirs: list[str] = []
        self.extract = extract
        self.crs = Lazy.CRS.from_epsg(4326)

    def __enter__(self):
        self.dem_files, self.temp_dirs = open_dem_files(self.dem_paths, self.extract)
        return self

    def elevation(self, latitude: float, longitude: float) -> float | None:
        """Query elevation for a point using DEM files.

        Estimates elevation by finding the closest DEM pixels and performing interpolation.

        Args:
            latitude: Latitude of the point.
            longitude: Longitude of the point.

        Returns:
            Elevation in meters, or None if unavailable.
        """
        for i, dem_file in enumerate(self.dem_files):
            height, width = dem_file.shape
            lon, lat = Lazy.transform(self.crs, dem_file.crs, [longitude], [latitude])
            rowf, colf = Lazy.rowcol(dem_file.transform, lon[0], lat[0], op=lambda v: v)
            row, col = int(rowf), int(colf)
            if 0 <= row < height and 0 <= col < width:
                rows = (max(row - 1, 0), min(row + 2, height))
                cols = (max(col - 1, 0), min(col + 2, width))
                dem = dem_file.read(
                    1, window=Lazy.Window.from_slices(rows, cols)
                ).copy()
                if dem.size:
                    if i > 0:  # Move file to index 0 (likely used for next query)
                        self.dem_files.insert(0, self.dem_files.pop(i))
                    if dem.size == 1:
                        return float(dem[0, 0])
                    if dem_file.nodata is not None:
                        dem[dem == dem_file.nodata] = math.nan

                    elevation = Lazy.interpn(
                        (range(*rows), range(*cols)),
                        dem[..., None],
                        [[rowf - 0.5, colf - 0.5]],
                        method="slinear",
                        bounds_error=False,
                        fill_value=None,
                    )[0, 0]
                    if math.isnan(elevation):
                        return None
                    return float(elevation)
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        for dem_file in self.dem_files:
            dem_file.close()
        self.dem_files.clear()
        for tmpdir in self.temp_dirs:
            if os.path.isdir(tmpdir):
                shutil.rmtree(tmpdir)
        self.temp_dirs.clear()


def add_elevation_to_gpx(
    gpx: GPX,
    dem_paths: Sequence[PathLike],
    overwrite: bool = False,
    extract: bool = False,
) -> int:
    """Add elevation data to a GPX file using DEM files.

    Args:
        dem_paths: List of paths to DEM files.
        overwrite: If True, overwrite existing elevation data.
        extract: If True, extract archive contents before processing.

    Returns:
        The number of points with elevation updates
    """
    point_updates = 0
    with ElevationDataManager(dem_paths, extract) as elevation:
        for point in gpx.points():
            if overwrite or point.elevation is None:
                value = elevation.elevation(point.latitude, point.longitude)
                if value is not None:
                    point.elevation = value
                    point_updates += 1
    return point_updates
