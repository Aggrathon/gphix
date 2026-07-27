import tarfile
import zipfile

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

pytestmark = pytest.mark.filterwarnings("ignore:Setting the shape:DeprecationWarning")

from gphix.elevation import ElevationDataManager, add_elevation_to_gpx
from gphix.gpx import GPX


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
    elevations: np.ndarray,
):
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


def test_query_elevation_from_dem_file(tmp_path):
    """Test querying elevation data from a single DEM file."""
    elevation = 130.0
    tif_path = tmp_path / "dem.tif"
    create_tif_point(tif_path, 48.9, 2.3, elevation)
    with ElevationDataManager([tif_path]) as mgr:
        assert mgr.elevation(48.9, 2.3) == pytest.approx(elevation, abs=0.1)


def test_query_multiple_dem_files(tmp_path):
    """Test querying elevation from multiple DEM files."""
    tif_path = tmp_path / "a.tif"
    create_tif_point(tif_path, 48.9, 2.3, 130.0)
    tif_path2 = tmp_path / "b.tif"
    create_tif_point(tif_path2, 51.5, -0.1, 125.0)
    with ElevationDataManager([tif_path, tif_path2]) as mgr:
        assert mgr.elevation(48.9, 2.3) == pytest.approx(130.0, abs=0.1)
        assert mgr.elevation(51.5, -0.1) == pytest.approx(125.0, abs=0.1)


def test_interpolate_elevations(tmp_path):
    """Test slinear interpolation with a multi-pixel DEM."""
    elevations = np.array(
        [
            [100.0, 102.0, 101.0],
            [103.0, 104.0, 105.0],
            [108.0, 107.0, 106.0],
        ],
        dtype=np.float32,
    )
    west, south, east, north = 2.2940, 48.8580, 2.2950, 48.8590
    tif_path = tmp_path / "multi.tif"
    create_tif_grid(tif_path, west, south, east, north, elevations)

    with ElevationDataManager([tif_path]) as mgr:
        assert mgr.elevation(48.8585, 2.2945) == pytest.approx(104.0, abs=0.01)
        result = mgr.elevation(48.8585, 2.29425)
        assert result is not None
        assert 102.0 < result < 106.0
        assert mgr.elevation(48.8582, 2.2942) is not None
        assert mgr.elevation(48.8587, 2.2948) is not None
        assert mgr.elevation(48.8595, 2.2955) is None


@pytest.mark.parametrize("fmt", ["zip", "tar"])
def test_query_archive(fmt, tmp_path):
    """Test querying elevation from ZIP and TAR archives."""
    a_path = tmp_path / "a.tif"
    b_path = tmp_path / "b.tif"
    create_tif_point(a_path, 48.9, 2.3, 175.0)
    create_tif_point(b_path, 51.5, -0.1, 124.0)

    if fmt == "zip":
        archive_path = tmp_path / "test.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.write(a_path, "a.tif")
            zf.write(b_path, "tmp/b.tif")
    else:
        archive_path = tmp_path / "test.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(a_path, "a.tif")
            tf.add(b_path, "tmp/b.tif")

    for extract in (False, True):
        with ElevationDataManager([archive_path], extract=extract) as mgr:
            assert mgr.elevation(48.9, 2.3) == 175.0
            assert mgr.elevation(51.5, -0.1) == 124.0


def test_add_elevation_partial_coverage(tmp_path):
    """Test that points outside DEM coverage keep their original values."""
    gpx = GPX()
    gpx.add_track().add_points((48.9, 2.3), (51.5, -0.1))

    tif_path = tmp_path / "dem.tif"
    create_tif_point(tif_path, 48.9, 2.3, 130.0)

    updates = add_elevation_to_gpx(gpx, [tif_path])
    assert updates == 1

    points = list(gpx.points())
    assert points[0].elevation == pytest.approx(130.0, abs=0.1)
    assert points[1].elevation is None


def test_add_elevation_multiple_tracks(tmp_path):
    """Test adding elevation across multiple tracks in a GPX file."""
    gpx = GPX()
    gpx.add_track().add_points((48.85, 2.3), (48.9, 2.35))
    gpx.add_track().add_points((51.5, -0.1), (51.55, -0.05))

    elevations = np.full((3, 3), 100.0, dtype=np.float32)
    tif_path = tmp_path / "dem.tif"
    create_tif_grid(tif_path, 2.2, 48.8, 2.6, 49.1, elevations)

    updates = add_elevation_to_gpx(gpx, [tif_path])
    assert updates == 2

    segments = gpx.segments()
    assert all(p.elevation == 100.0 for p in segments[0].points())
    assert all(p.elevation is None for p in segments[1].points())


def test_add_elevation_mixed_existing_and_missing(tmp_path):
    """Test overwrite with partial coverage: some points have existing elevation,
    some are missing, and some are outside DEM coverage."""
    gpx = GPX()
    gpx.add_track().add_points((48.9, -2.3, 50.0), (48.95, -2.35), (51.5, 0.1))

    tif_path = tmp_path / "dem.tif"
    elevations = np.full((3, 3), 200.0, dtype=np.float32)
    create_tif_grid(tif_path, -2.2, 48.8, -2.6, 49.1, elevations)

    updates = add_elevation_to_gpx(gpx, [tif_path], overwrite=False)
    assert updates == 1
    points = list(gpx.points())
    assert points[0].elevation == 50.0
    assert points[1].elevation == 200.0
    assert points[2].elevation is None

    updates = add_elevation_to_gpx(gpx, [tif_path], overwrite=True)
    assert updates == 2
    points = list(gpx.points())
    assert points[0].elevation == 200.0
    assert points[1].elevation == 200.0
    assert points[2].elevation is None


def test_add_elevation_with_stats(tmp_path):
    """Test adding elevation and verifying stats reflect the changes."""
    gpx = GPX()
    gpx.add_track().add_points((-48.85, 2.3), (-48.875, 2.3), (-48.9, 2.3))

    elevations = np.array([[100.0, 105.0], [110.0, 115.0]], dtype=np.float32)
    tif_path = tmp_path / "dem.tif"
    create_tif_grid(tif_path, 2.2, -48.8, 2.4, -49.0, elevations)

    stats_before = gpx.stats()
    updates = add_elevation_to_gpx(gpx, [tif_path])
    assert updates == stats_before.points

    stats_after = gpx.stats()
    assert stats_after.min_elev is not None
    assert stats_after.max_elev is not None
    assert stats_after.min_elev < stats_after.max_elev
    assert stats_after.tracks == 1
    assert stats_after.distance > stats_before.distance
