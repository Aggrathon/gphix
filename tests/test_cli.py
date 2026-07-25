from datetime import UTC, datetime
from io import StringIO

from gphix.cli import _cmd_stats, _format_distance, _format_duration, main

from .utils import create_gpx_file


def test_cmd_stats_no_time_no_elevation(tmp_path):
    """Test stats command with minimal GPX (no time or elevation)."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path)

    buf = StringIO()
    _cmd_stats(gpx_path, buf)
    output = buf.getvalue()

    assert "Points: 3" in output
    assert "Distance:" in output
    assert "Duration: N/A" in output
    assert "Time: N/A" in output
    assert "Elevation: N/A" in output
    assert "BBox:" in output


def test_cmd_stats_with_time_and_elevation(tmp_path):
    """Test stats command with time and elevation data."""
    t0 = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2024, 6, 1, 10, 5, 0, tzinfo=UTC)
    t2 = datetime(2024, 6, 1, 10, 10, 0, tzinfo=UTC)

    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path, elevation=[100.0, 200.0, 300.0], time=[t0, t1, t2])

    buf = StringIO()
    main(["stats", str(gpx_path)], out=buf)
    output = buf.getvalue()

    assert "Points: 3" in output
    assert "Duration:" in output
    assert "Start:" in output
    assert "End:" in output
    assert "Elevation: 100 – 300 m" in output


def test_format_distance():
    # Test _format_distance for values below 1 km.
    assert _format_distance(500.0) == "500 m"
    assert _format_distance(10.0) == "10 m"
    # Test _format_distance for values >= 1 km.
    assert _format_distance(1500.0) == "1.50 km"
    assert _format_distance(10500.0) == "10.50 km"


def test_format_duration():
    """Test _format_duration helper."""
    assert _format_duration(0) == "0s"
    assert _format_duration(45) == "45s"
    assert _format_duration(65) == "1m 5s"
    assert _format_duration(3661) == "1h 1m 1s"
    assert _format_duration(7265) == "2h 1m 5s"


def test_main_help():
    """Test that main prints help when no command given."""
    buf = StringIO()
    main([], out=buf)
    output = buf.getvalue()
    assert "gphix" in output
    assert "stats" in output
