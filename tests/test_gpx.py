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
    assert isinstance(stats.distance, float)
    assert stats.duration == 0.0
    assert stats.start_time is None
    assert stats.end_time is None
    assert stats.min_lat == 40.7128
    assert stats.max_lat == 51.5074
    assert stats.min_lon == -74.006
    assert stats.max_lon == 2.2945
    assert stats.min_elev is None
    assert stats.max_elev is None
    assert stats.tracks == 1


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

    assert stats.duration == (t2 - t0).total_seconds()
    assert stats.start_time == t0
    assert stats.end_time == t2


def test_stats_empty(tmp_path):
    """Test stats for a GPX file with no points."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, [])
    gpx = GPX(gpx_path)
    stats = gpx.stats()

    assert stats.points == 0
    assert stats.distance == 0.0
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

    gpx.write(output_gpx)
    gpx2 = GPX(output_gpx)
    assert len(list(gpx.points())) == len(list(gpx2.points()))


def test_merge_tracks(tmp_path):
    """Test that tracks from multiple files are preserved."""
    f1 = tmp_path / "a.gpx"
    f2 = tmp_path / "b.gpx"
    f3 = tmp_path / "c.gpx"

    create_gpx_file(f1, coords=[(40.0, -74.0)])
    create_gpx_file(f2, coords=[(41.0, -73.0)])
    create_gpx_file(f3, coords=[(50.0, 1.0)])

    merged = GPX.merge([f1, f2, f3])
    assert len(merged.root.findall("gpx:trk", merged.namespaces)) == 3
    assert len(list(merged.points())) == 3


def test_merge_multi_track_files(tmp_path):
    """Test merging files that each contain multiple tracks."""
    gpx1 = GPX(None)
    gpx1.add_track().add_points([(40.0, -74.0), (40.1, -73.9)])
    gpx1.add_track().add_points([(41.0, -73.0), (41.1, -72.9)])

    gpx2 = GPX(None)
    gpx2.add_track().add_points([(50.0, 1.0), (50.1, 1.1)])
    gpx2.add_track().add_points([(51.0, 2.0), (51.1, 2.1)])

    merged = GPX.merge([gpx1, gpx2])
    assert len(merged.root.findall("gpx:trk", merged.namespaces)) == 4
    assert len(list(merged.points())) == 8


def test_merge_waypoints(tmp_path):
    """Test that waypoints from multiple sources are combined."""
    gpx1 = GPX(None)
    gpx1.add_waypoint(50.0, 1.0).elevation = 50.0

    gpx2 = GPX(None)
    gpx2.add_waypoint(51.0, 2.0)
    gpx2.add_waypoint(52.0, 3.0).elevation = 100.0

    merged = GPX.merge([gpx1, gpx2])
    assert len(list(merged.points())) == 3


def test_merge_single_file(tmp_path):
    """Merging one file returns an equivalent GPX."""
    f = tmp_path / "input.gpx"
    create_gpx_file(f, elevation=[10.0, 20.0, 30.0])

    orig = GPX(f)
    merged = GPX.merge([f])
    assert merged.stats() == orig.stats()
