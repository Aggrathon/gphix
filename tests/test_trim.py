import pytest

from gphix.gpx import GPX

from .utils import Point, create_gpx_file


def test_trim_percent_simple(tmp_path):
    """Trim 0.2 (20 %) from each end of a single-track file."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, [Point(40.0 + i, -74.0) for i in range(5)])

    gpx = GPX(gpx_path)
    trimmed = gpx.trim(start=0.2, end=0.2)
    assert len(list(trimmed.points())) == 3


def test_trim_percent_zero(tmp_path):
    """Trim 0 % from each end should keep everything."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, [Point(40.0 + i, -74.0) for i in range(5)])

    gpx = GPX(gpx_path)
    trimmed = gpx.trim(start=0, end=0)
    assert len(list(trimmed.points())) == 5


def test_trim_percent_multi_track(tmp_path):
    """Trim 0.2 (20 %) from each end across multiple nearby tracks."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path,
        [Point(40.0, -74.0), Point(40.1, -73.9), Point(40.2, -73.8)],
        [Point(40.3, -73.7), Point(40.4, -73.6), Point(40.5, -73.5)],
        [Point(40.6, -73.4), Point(40.7, -73.3), Point(40.8, -73.2)],
    )

    trimmed = GPX(gpx_path).trim(start=0.2, end=0.2)
    stats = trimmed.stats()
    assert stats.points == 5
    assert stats.tracks == 3


def test_trim_time(tmp_path):
    """Trim 1 minute from start and 1 minute from end (time mode)."""
    coords = [(40.0 + i, -74.0) for i in range(5)]

    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path, [Point(c[0], c[1], time=i * 60) for i, c in enumerate(coords)]
    )

    gpx = GPX(gpx_path)
    trimmed = gpx.trim(start=60, end=60, by_time=True)
    stats = trimmed.stats()
    assert stats.points == 3
    assert stats.duration == 120


def test_trim_time_no_time_data_returns_same(tmp_path):
    """Trimming by time on a file without time data returns unchanged."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, [Point(40.0, -74.0), Point(41.0, -73.0)])

    gpx = GPX(gpx_path)
    trimmed = gpx.trim(start=60, by_time=True)
    assert gpx.stats() == trimmed.stats()


def test_trim_distance(tmp_path):
    """Trim 1000 m from start and 1000 m from end."""
    create_gpx_file(tmp_path / "input.gpx", [Point(i, 0.0) for i in range(5)])

    trimmed = GPX(tmp_path / "input.gpx").trim(start=1000, end=1000, by_distance=True)
    stats = trimmed.stats()

    assert stats.points == 3
    assert stats.tracks == 1
    assert stats.min_lat == 1.0
    assert stats.max_lat == 3.0
    assert stats.min_lon == 0.0
    assert stats.max_lon == 0.0
    assert stats.distance > 200_000
    assert stats.distance < 250_000


def test_trim_multi_track_sorts_by_time(tmp_path):
    """Tracks are sorted by earliest timestamp before trimming."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path,
        [Point(51.5 + i * 0.01, -0.1 + i * 0.01, time=(10 + i) * 60) for i in range(3)],
        [Point(40.0 + i, -74.0, time=i * 50) for i in range(5)],
    )

    trimmed = GPX(gpx_path).trim(start=60, end=15, by_time=True)
    stats = trimmed.stats()
    assert stats.points == 5
    assert stats.duration == 160


def test_trim_drops_completely_removed_track(tmp_path):
    """A track entirely in the trimmed zone is dropped."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path,
        [Point(40.0 + i * 0.001, -74.0, time=i * 10) for i in range(5)],
        [Point(45.0, -50.0, time=50)],
        [Point(40.0 + i * 0.01, -74.0, time=60 + i * 10) for i in range(5)],
    )

    trimmed = GPX(gpx_path).trim(start=30, end=30, by_time=True)
    assert len(list(trimmed.points())) == 5


def test_trim_round_trip(tmp_path):
    """Trimmed output can be written and re-parsed."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path,
        [Point(40.0 + i, -74.0, ele=100.0 + i * 10) for i in range(5)],
    )

    trimmed = GPX(gpx_path).trim(start=0.2, end=0.2)
    output_path = tmp_path / "trimmed.gpx"
    trimmed.write(output_path)
    gpx2 = GPX(output_path)
    assert gpx2.stats() == trimmed.stats()


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
    create_gpx_file(gpx_path, [Point(40.0, -74.0)])
    with pytest.raises(ValueError):
        GPX(gpx_path).trim(start=10, end=10, by_time=True, by_distance=True)
