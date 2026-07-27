"""
Tests for the CLI.
Intended to make sure the commands still work.
Not for checking every detail of the algorithms (tested elsewhere).
Hence, every use-case should only have a limited number of tests.
"""

from io import BytesIO, StringIO
from pathlib import Path

from gphix.cli import _format_distance, _format_duration, main
from gphix.gpx import GPX

from .utils import Point, create_gpx_file


def _file_to_stdin(path: Path) -> BytesIO:
    """Read a file and return its contents as a ``BytesIO`` for stdin."""
    with open(path, "rb") as f:
        return BytesIO(f.read())


def _assert_raw_xml(buf: StringIO, *exclude: str) -> None:
    """Assert *buf* contains raw XML with no summary text.

    Args:
        buf: A ``StringIO`` buffer whose value will be checked.
        exclude: Strings that must not appear.
    """
    output = buf.getvalue()
    assert "<?xml" in output
    assert "<gpx" in output
    assert "</gpx>" in output
    for text in exclude:
        assert text not in output
    assert "Points:" not in output
    assert "Tracks:" not in output


def test_cmd_stats_stdin(tmp_path):
    """Test stats command with minimal and full GPX data."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path)

    buf = StringIO()
    main(["stats", "-"], out=buf, stdin=_file_to_stdin(gpx_path))
    output = buf.getvalue()

    assert "Points: 3" in output
    assert "Distance:" in output
    assert "Duration: 0s" in output
    assert "Time: N/A" in output
    assert "Elevation: N/A" in output
    assert "BBox:" in output


def test_cmd_stats_with_time_and_elevation(tmp_path):
    """Test stats command with time and elevation data."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path,
        [
            Point(48.8, 2.2, 100.0, 0),
            Point(51.5, -0.1, 200.0, 300),
            Point(40.7, -74.0, 300.0, 600),
        ],
    )

    buf = StringIO()
    main(["stats", str(gpx_path)], out=buf)
    output = buf.getvalue()

    assert "Points: 3" in output
    assert "Duration: 10m" in output
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


def test_cmd_merge(tmp_path):
    """Test the merge CLI command."""
    f1 = tmp_path / "a.gpx"
    f2 = tmp_path / "b.gpx"
    out = tmp_path / "merged.gpx"

    create_gpx_file(f1, [Point(40.0, -74.0)])
    create_gpx_file(f2, [Point(51.0, 1.0)])

    buf = StringIO()
    main(["merge", str(f1), str(f2), "-o", str(out)], out=buf)
    output = buf.getvalue()

    assert "Merged 2 file" in output
    assert "Points: 2" in output
    assert "Tracks: 2" in output

    merged = GPX(out)
    assert len(list(merged.points())) == 2


def test_cmd_merge_stdout(tmp_path):
    """Test that merge with -o prints raw XML to stdout."""
    f1 = tmp_path / "a.gpx"
    f2 = tmp_path / "b.gpx"

    create_gpx_file(f1, [Point(40.0, -74.0)])
    create_gpx_file(f2, [Point(51.0, 1.0)])

    buf = StringIO()
    main(["merge", str(f1), str(f2), "-o", "-"], out=buf)

    _assert_raw_xml(buf, "Merged")


def test_cmd_trim_distance_mode(tmp_path):
    """Test trim with --distance flag."""
    create_gpx_file(tmp_path / "input.gpx", [Point(i, 0.0) for i in range(5)])

    buf = StringIO()
    main(
        [
            "trim",
            str(tmp_path / "input.gpx"),
            "-o",
            "-",
            "--distance",
            "--start",
            "1000",
            "--end",
            "1000",
        ],
        out=buf,
    )
    _assert_raw_xml(buf, "Trimmed")


def test_cmd_trim_time_mode(tmp_path):
    """Test trim with --time flag."""
    path = tmp_path / "input.gpx"
    create_gpx_file(path, [Point(40.0 + i, -74.0, time=i * 60) for i in range(5)])

    buf = StringIO()
    main(
        [
            "trim",
            str(path),
            "-o",
            "-",
            "--time",
            "--start",
            "60",
            "--end",
            "60",
        ],
        out=buf,
    )
    _assert_raw_xml(buf)


def test_cmd_trim_stdin(tmp_path):
    """Test trim reading from stdin."""
    gpx_path = tmp_path / "input.gpx"
    out_path = tmp_path / "trimmed.gpx"
    create_gpx_file(gpx_path, [Point(40.0 + i, -74.0) for i in range(5)])

    buf = StringIO()
    main(
        ["trim", "-", "-o", str(out_path), "--start=20", "--end=20"],
        out=buf,
        stdin=_file_to_stdin(gpx_path),
    )

    output = buf.getvalue()
    assert "Trimmed" in output
    trimmed = GPX(out_path)
    assert len(list(trimmed.points())) == 3


def test_insert_file_stdout(tmp_path):
    """Test insert with file input and stdout (single point smoke test)."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path)
    buf = StringIO()
    main(["insert", str(gpx_path), "-o", "-", "48.8,2.2"], out=buf)
    _assert_raw_xml(buf, "Inserted")


def test_insert_stdin_file(tmp_path):
    """Test insert with stdin input and file output (all point combos)."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path)
    out_path = tmp_path / "output.gpx"

    main(
        [
            "insert",
            "-",
            "-o",
            str(out_path),
            "48.8,2.2",
            "48.9,2.3,100.0",
            "49.0,2.4,2024-01-01T12:05:00+00:00",
            "49.1,2.5,300.0,2024-01-01T12:10:00+00:00",
        ],
        stdin=_file_to_stdin(gpx_path),
    )

    gpx = GPX(out_path)
    stats = gpx.stats()
    assert stats.tracks == 2
    assert stats.points == 7

    new_points = list(gpx.points())[3:]

    assert new_points[0].latitude == 48.8
    assert new_points[0].longitude == 2.2
    assert new_points[0].elevation is None
    assert new_points[0].time is None

    assert new_points[1].elevation == 100.0
    assert new_points[1].time is None

    assert new_points[2].time is not None
    assert new_points[2].elevation is None

    assert new_points[3].elevation == 300.0
    assert new_points[3].time is not None
