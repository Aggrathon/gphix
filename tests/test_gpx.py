from datetime import UTC, datetime

from gphix.gpx import GPX

from .utils import create_gpx_file


def test_stats_basic(tmp_path):
    """Test that stats returns correct values for a simple GPX file."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path)
    gpx = GPX(gpx_path)
    stats = gpx.stats()

    assert stats.points == 3
    assert isinstance(stats.distance_m, float)
    assert stats.duration_s is None
    assert stats.start_time is None
    assert stats.end_time is None
    assert stats.min_lat == 40.7128
    assert stats.max_lat == 51.5074
    assert stats.min_lon == -74.006
    assert stats.max_lon == 2.2945
    assert stats.min_elev is None
    assert stats.max_elev is None


def test_stats_with_elevation(tmp_path):
    """Test stats with a list of custom elevation values."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, elevation=[0.0, 50.0, 200.0])
    gpx = GPX(gpx_path)
    stats = gpx.stats()

    assert stats.min_elev == 0.0
    assert stats.max_elev == 200.0


def test_stats_with_time(tmp_path):
    """Test stats with time data present."""

    t0 = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2024, 6, 1, 10, 5, 0, tzinfo=UTC)
    t2 = datetime(2024, 6, 1, 10, 10, 0, tzinfo=UTC)

    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, time=[t0, t1, t2])
    gpx = GPX(gpx_path)
    stats = gpx.stats()

    assert stats.duration_s == (t2 - t0).total_seconds()
    assert stats.start_time == t0
    assert stats.end_time == t2


def test_stats_empty(tmp_path):
    """Test stats for a GPX file with no points."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, [])
    gpx = GPX(gpx_path)
    stats = gpx.stats()

    assert stats.points == 0
    assert stats.distance_m == 0.0
    assert stats.min_elev is None
    assert stats.max_elev is None


def test_gpx_class_parse(tmp_path):
    """Test the GPX class for parsing GPX files."""
    input_gpx = tmp_path / "input.gpx"
    output_gpx = tmp_path / "output.gpx"

    create_gpx_file(input_gpx, elevation=True)
    gpx = GPX(input_gpx)
    points = list(gpx.points())
    assert len(points) == 3

    for point in points:
        assert point.elevation == 100.0

    assert abs(points[0].latitude - 48.8584) < 0.0001
    assert abs(points[0].longitude - 2.2945) < 0.0001

    assert abs(points[1].latitude - 51.5074) < 0.0001
    assert abs(points[1].longitude - (-0.1278)) < 0.0001

    assert abs(points[2].latitude - 40.7128) < 0.0001
    assert abs(points[2].longitude - (-74.0060)) < 0.0001

    # Test writing with GPX class
    gpx.write(str(output_gpx))
    gpx2 = GPX(output_gpx)
    points2 = list(gpx2.points())
    assert len(points2) == 3
