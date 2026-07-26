from io import BytesIO, StringIO

from gphix.cli import _cmd_stats, _format_distance, _format_duration, main
from gphix.gpx import GPX

from .utils import Point, create_gpx_file


def test_cmd_stats_no_time_no_elevation(tmp_path):
    """Test stats command with minimal GPX (no time or elevation)."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path)

    buf = StringIO()
    _cmd_stats(gpx_path, buf)
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
    output = buf.getvalue()

    # Should be raw XML, no summary text
    assert "<?xml" in output
    assert "<gpx" in output
    assert "</gpx>" in output
    assert "Merged" not in output
    assert "Points:" not in output
    assert "Tracks:" not in output


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
    output = buf.getvalue()
    assert "<?xml" in output
    assert "<gpx" in output
    assert "</gpx>" in output
    assert "Trimmed" not in output
    assert "Points:" not in output
    assert "Tracks:" not in output


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
    output = buf.getvalue()
    assert "<?xml" in output
    assert "<gpx" in output
    assert "</gpx>" in output
    assert "Trimmed" not in output
    assert "Points:" not in output
    assert "Tracks:" not in output


def test_cmd_trim_stdin(tmp_path):
    """Test trim reading from stdin."""
    gpx_path = tmp_path / "input.gpx"
    out_path = tmp_path / "trimmed.gpx"
    create_gpx_file(gpx_path, [Point(40.0 + i, -74.0) for i in range(5)])

    with open(gpx_path, "rb") as f:
        gpx_content = f.read()

    buf = StringIO()
    bin = BytesIO(gpx_content)
    main(
        ["trim", "-", "-o", str(out_path), "--start=20", "--end=20"], out=buf, stdin=bin
    )

    output = buf.getvalue()
    assert "Trimmed" in output
    trimmed = GPX(out_path)
    assert len(list(trimmed.points())) == 3
