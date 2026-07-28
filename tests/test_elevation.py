import tarfile
import zipfile

import numpy as np
import pytest

from gphix.elevation import ElevationDataManager, GPXInterpolator, add_elevation_to_gpx
from gphix.gpx import GPX

from .utils import Point, create_gpx_file, create_tif_grid, create_tif_point, no_np_warn


@no_np_warn()
def test_query_elevation_from_dem_file(tmp_path):
    """Test querying elevation data from a single DEM file."""
    elevation = 130.0
    tif_path = tmp_path / "dem.tif"
    create_tif_point(tif_path, 48.9, 2.3, elevation)
    with ElevationDataManager([tif_path]) as mgr:
        assert mgr.elevation(48.9, 2.3) == pytest.approx(elevation, abs=0.1)


@no_np_warn()
def test_query_multiple_dem_files(tmp_path):
    """Test querying elevation from multiple DEM files."""
    tif_path = tmp_path / "a.tif"
    create_tif_point(tif_path, 48.9, 2.3, 130.0)
    tif_path2 = tmp_path / "b.tif"
    create_tif_point(tif_path2, 51.5, -0.1, 125.0)
    with ElevationDataManager([tif_path, tif_path2]) as mgr:
        assert mgr.elevation(48.9, 2.3) == pytest.approx(130.0, abs=0.1)
        assert mgr.elevation(51.5, -0.1) == pytest.approx(125.0, abs=0.1)


@no_np_warn()
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
@no_np_warn()
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


@no_np_warn()
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


@no_np_warn()
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


@no_np_warn()
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


@no_np_warn()
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


def test_gpx_reference_provider_exact_vertex():
    """GPX reference returns elevation of an exact vertex."""
    gpx = GPX()
    gpx.add_track().add_points((48.8, 2.3, 100.0), (48.9, 2.3, 200.0))
    provider = GPXInterpolator([gpx], radius=50.0)
    assert provider.elevation(48.8, 2.3) == 100.0
    assert provider.elevation(48.9, 2.3) == 200.0


def test_gpx_reference_provider_perpendicular():
    """GPX reference projects onto a diagonal segment."""
    gpx = GPX()
    gpx.add_track().add_points((48.8, 2.3, 100.0), (48.81, 2.31, 200.0))
    provider = GPXInterpolator([gpx], radius=50.0)
    result = provider.elevation(48.805 + 0.0004, 2.305)
    assert result is not None
    assert 140 < result < 160


def test_gpx_reference_provider_outside_cutoff():
    """GPX reference returns None when perpendicular distance exceeds cutoff."""
    gpx = GPX()
    gpx.add_track().add_points((48.8, 2.3, 100.0), (48.9, 2.3, 200.0))
    provider = GPXInterpolator([gpx], radius=50.0)
    assert provider.elevation(49.5, 2.3) is None


def test_gpx_reference_provider_no_elevation_vertices():
    """GPX reference skips edges where either endpoint lacks elevation."""
    gpx = GPX()
    gpx.add_track().add_points((48.8, 2.3), (48.9, 2.3, 200.0))
    provider = GPXInterpolator([gpx], radius=50.0)
    assert provider.elevation(48.8, 2.3) is None


def test_gpx_reference_provider_multiple_tracks():
    """GPX reference merges multiple tracks and picks closest."""
    gpx = GPX()
    gpx.add_track().add_points((48.8, 2.3, 100.0), (48.8, 2.4, 150.0))
    gpx.add_track().add_points((51.5, -0.1, 50.0), (51.5, -0.2, 60.0))
    provider = GPXInterpolator([gpx], radius=50.0)
    assert provider.elevation(48.8, 2.3) == 100.0
    assert provider.elevation(51.5, -0.1) == 50.0


@no_np_warn()
def test_elevation_manager_gpx_first_then_dem(tmp_path):
    """ElevationDataManager uses GPX first, DEM as fallback."""
    gpx_path = tmp_path / "ref.gpx"
    create_gpx_file(gpx_path, [Point(48.8, 2.3, 100.0), Point(48.9, 2.4, 200.0)])
    tif_path = tmp_path / "dem.tif"
    create_tif_point(tif_path, 48.9, 2.3, 130.0)

    with ElevationDataManager([gpx_path, tif_path]) as mgr:
        assert mgr.elevation(48.8, 2.3) == 100.0
        assert mgr.elevation(48.9, 2.3) == 130.0


def test_elevation_manager_gpx_in_zip(tmp_path):
    """GPX files inside a zip archive are extracted and used as reference."""
    gpx_path = tmp_path / "ref.gpx"
    create_gpx_file(gpx_path, [Point(48.8, 2.3, 999.0), Point(48.81, 2.31, 888.0)])
    tif_path = tmp_path / "dem.tif"
    create_tif_point(tif_path, 48.8, 2.3, 130.0)

    archive_path = tmp_path / "mixed.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.write(tif_path, "dem.tif")
        zf.write(gpx_path, "ref.gpx")

    with ElevationDataManager([archive_path]) as mgr:
        assert mgr.elevation(48.8, 2.3) == 999.0
        result = mgr.elevation(48.805, 2.305)
        assert result is not None
        assert result > 500
        result2 = mgr.elevation(48.95, 2.3)
        assert result2 is None


def test_add_elevation_from_gpx_reference(tmp_path):
    """Test that GPX references are used for elevation assignment."""
    gpx = GPX()
    gpx.add_track().add_points((48.8, 2.3), (48.85, 2.35), (48.9, 2.4))

    ref_path = tmp_path / "ref.gpx"
    create_gpx_file(
        ref_path,
        [
            Point(48.8, 2.3, 100.0),
            Point(48.85, 2.35, 150.0),
            Point(48.9, 2.4, 200.0),
        ],
    )

    updates = add_elevation_to_gpx(gpx, [ref_path])
    assert updates == 3

    points = list(gpx.points())
    assert points[0].elevation == 100.0
    assert points[1].elevation == 150.0
    assert points[2].elevation == 200.0


def test_gpx_reference_radius_parameter(tmp_path):
    """Test that the radius parameter controls how far GPX covers."""
    gpx = GPX()
    gpx.add_track().add_points((48.8, 2.3, 100.0), (48.9, 2.3, 200.0))

    provider_large = GPXInterpolator([gpx], radius=10000.0)
    result = provider_large.elevation(48.85, 2.3)
    assert result == pytest.approx(150.0, abs=0.5)

    provider_small = GPXInterpolator([gpx], radius=10.0)
    result = provider_small.elevation(48.85, 2.301)
    assert result is None
