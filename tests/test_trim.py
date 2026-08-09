import pytest

from gphix.trim import trim

from .utils import Point, create_gpx


@pytest.mark.parametrize(
    "fraction,points", [(0.2, 5), (0.0, 5)], ids=("fraction", "zero")
)
def test_trim_percent(fraction: float, points: int):
    """Trim a percent from each end of a single-track file."""
    gpx = create_gpx([Point(40.0 + i, -74.0) for i in range(points)])
    trim(gpx, start=fraction, end=fraction, start_unit="p", end_unit="p")
    assert len(list(gpx.points())) == points - round(points * fraction * 2)


def test_trim_percent_multi_track():
    """Trim 0.2 (20 %) from each end across multiple nearby tracks."""
    gpx = create_gpx(
        [Point(40.0, -74.0), Point(40.1, -73.9), Point(40.2, -73.8)],
        [Point(40.3, -73.7), Point(40.4, -73.6), Point(40.5, -73.5)],
        [Point(40.6, -73.4), Point(40.7, -73.3), Point(40.8, -73.2)],
    )
    trim(gpx, start=0.2, end=0.2, start_unit="p", end_unit="p")
    stats = gpx.stats()
    assert len(gpx.segments()[0]) == 1
    assert len(gpx.segments()[1]) == 3
    assert len(gpx.segments()[2]) == 1
    assert stats.points == 5
    assert stats.tracks == 3
    trim(gpx, start=0.2, end=0.2, start_unit="p", end_unit="p")
    assert len(gpx.segments()) == 1  # the segments iterator skips empty segments
    assert len(gpx.segments()[0]) == 3


def test_trim_time():
    """Trim 1 minute from start and 1 minute from end (time mode)."""
    coords = [(40.0 + i, -74.0) for i in range(5)]
    gpx = create_gpx([Point(c[0], c[1], time=i * 60) for i, c in enumerate(coords)])
    trim(gpx, start=60, end=60, start_unit="s", end_unit="s")
    stats = gpx.stats()
    assert stats.points == 3
    assert stats.duration == 120


def test_trim_distance():
    """Trim 1000 m from start and 1000 m from end."""
    gpx = create_gpx([Point(i, 0.0) for i in range(5)])
    orig_stats = gpx.stats()
    trim(gpx, start=1000, end=1000, start_unit="m", end_unit="m")
    stats = gpx.stats()
    assert stats.points == 3
    assert stats.tracks == 1
    assert stats.distance > 200_000
    assert stats.distance < orig_stats.distance - 2000


def test_trim_multi_track_sorts_by_time():
    """Tracks are sorted by earliest timestamp before trimming."""
    gpx = create_gpx(
        [Point(51.5 + i * 0.01, -0.1 + i * 0.01, time=(10 + i) * 60) for i in range(3)],
        [Point(40.0 + i, -74.0, time=i * 50) for i in range(5)],
    )
    trim(gpx, start=60, end=15, start_unit="s", end_unit="s")
    stats = gpx.stats()
    assert stats.points == 5
    assert stats.duration == 160


def test_trim_index():
    """Trim 1 point from start and 2 from end by index."""
    gpx = create_gpx([Point(40.0 + i, -74.0) for i in range(10)])
    trim(gpx, start=1, end=2, start_unit="i", end_unit="i")
    assert len(list(gpx.points())) == 7
    trim(gpx, start=(0, 1), end=(0, 6))
    assert len(list(gpx.points())) == 6


def test_trim_cut_after_trimmed():
    """Trimming when start is after end raises."""
    gpx = create_gpx([Point(40.0 + i, -74.0) for i in range(5)])
    with pytest.raises(ValueError):
        trim(gpx, start=4, end=1, start_unit="i", end_unit="i")
