from datetime import UTC, datetime, timedelta

import pytest

from gphix.gpx import GPX

from .utils import create_gpx_file


def test_trim_percent_simple(tmp_path):
    """Trim 0.2 (20 %) from each end of a single-track file."""
    gpx_path = tmp_path / "input.gpx"
    coords = [(40.0 + i, -74.0) for i in range(5)]
    create_gpx_file(gpx_path, coords=coords)

    gpx = GPX(gpx_path)
    trimmed = gpx.trim(start=0.2, end=0.2)

    assert len(list(trimmed.points())) == 3


def test_trim_percent_zero(tmp_path):
    """Trim 0 % from each end should keep everything."""
    gpx_path = tmp_path / "input.gpx"
    coords = [(40.0 + i, -74.0) for i in range(5)]
    create_gpx_file(gpx_path, coords=coords)

    gpx = GPX(gpx_path)
    trimmed = gpx.trim(start=0, end=0)

    assert len(list(trimmed.points())) == 5


def test_trim_percent_multi_track(tmp_path):
    """Trim 0.2 (20 %) from each end across multiple nearby tracks."""
    coords_1 = [(40.0, -74.0), (40.001, -73.999), (40.002, -73.998)]
    coords_2 = [(40.003, -73.997), (40.004, -73.996), (40.005, -73.995)]
    coords_3 = [(40.006, -73.994), (40.007, -73.993), (40.008, -73.992)]

    gpx = GPX(None)
    for track_coords in [coords_1, coords_2, coords_3]:
        builder = gpx.add_track()
        builder.add_points(track_coords)

    trimmed = gpx.trim(start=0.2, end=0.2)
    pts = list(trimmed.points())

    assert len(pts) == 5


def test_trim_time(tmp_path):
    """Trim 1 minute from start and 1 minute from end (time mode)."""
    t0 = datetime.now(UTC)
    times = [t0 + timedelta(minutes=i) for i in range(5)]
    coords = [(40.0 + i, -74.0) for i in range(5)]

    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, coords=coords, time=times)

    gpx = GPX(gpx_path)
    trimmed = gpx.trim(start=60, end=60, by_time=True)

    assert len(list(trimmed.points())) == 3


def test_trim_time_no_time_data_returns_same(tmp_path):
    """Trimming by time on a file without time data returns unchanged."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, coords=[(40.0, -74.0), (41.0, -73.0)])

    gpx = GPX(gpx_path)
    trimmed = gpx.trim(start=60, by_time=True)

    assert gpx.stats() == trimmed.stats()


def test_trim_distance(tmp_path):
    """Trim 1000 m from start and 1000 m from end."""
    coords = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (4.0, 0.0)]
    create_gpx_file(tmp_path / "input.gpx", coords=coords)

    trimmed = GPX(tmp_path / "input.gpx").trim(start=1000, end=1000, by_distance=True)
    assert len(list(trimmed.points())) == 3


def test_trim_multi_track_sorts_by_time(tmp_path):
    """Tracks are sorted by earliest timestamp before trimming."""
    t0 = datetime.now(UTC)

    gpx1 = GPX(None)
    b = gpx1.add_track()
    for i in range(3):
        pt = b.add_point(40.0 + i, -74.0)
        pt.time = t0 + timedelta(minutes=i)

    gpx2 = GPX(None)
    b = gpx2.add_track()
    for i in range(3):
        pt = b.add_point(51.5 + i * 0.01, -0.1 + i * 0.01)
        pt.time = t0 + timedelta(minutes=10 + i)

    merged = GPX.merge([gpx2, gpx1])
    trimmed = merged.trim(start=15, end=15, by_time=True)
    assert len(list(trimmed.points())) == 4


def test_trim_drops_completely_removed_track(tmp_path):
    """A track entirely in the trimmed zone is dropped."""
    t0 = datetime.now(UTC)

    gpx = GPX(None)

    b = gpx.add_track()
    for i in range(5):
        pt = b.add_point(40.0 + i * 0.001, -74.0)
        pt.time = t0 + timedelta(seconds=i * 10)

    b = gpx.add_track()
    pt = b.add_point(45.0, -50.0)
    pt.time = t0 + timedelta(seconds=50)

    b = gpx.add_track()
    for i in range(5):
        pt = b.add_point(40.0 + 100 * 0.001 + i * 0.001, -74.0 + 100 * 0.001)
        pt.time = t0 + timedelta(seconds=60 + i * 10)

    trimmed = gpx.trim(start=30, end=30, by_time=True)
    assert len(list(trimmed.points())) == 5


def test_trim_empty_tracks(tmp_path):
    """Trimming a GPX with no tracks returns empty GPX."""
    gpx = GPX(None)
    trimmed = gpx.trim()
    assert len(list(trimmed.points())) == 0


def test_trim_preserves_metadata(tmp_path):
    """Trimmed output should preserve metadata from the original."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, metadata="<name>Test Track</name>")

    gpx = GPX(gpx_path)
    trimmed = gpx.trim(start=0.2, end=0.2)
    assert len(list(trimmed.root.findall("gpx:metadata", trimmed.namespaces))) == 1


def test_trim_by_time_and_distance_raises(tmp_path):
    """Specifying both by_time and by_distance raises ValueError."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, coords=[(40.0, -74.0)])
    with pytest.raises(ValueError):
        GPX(gpx_path).trim(start=10, end=10, by_time=True, by_distance=True)
