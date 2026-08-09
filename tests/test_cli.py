"""
Tests for the CLI.
Intended to make sure the commands still work.
Not for checking every detail of the algorithms (tested elsewhere).
Hence, every use-case should only have a limited number of tests.
"""

from io import BytesIO, StringIO
from pathlib import Path

from gphix.cli import main
from gphix.gpx import GPX, GPXMetadata

from .utils import Point, create_gpx_file, create_tif_grid, no_np_warn


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


def test_main_help():
    """Test that main prints help when no command given."""
    buf = StringIO()
    main([], out=buf)
    output = buf.getvalue()
    assert "gphix" in output
    assert "stats" in output
    assert "merge" in output
    assert "trim" in output
    assert "insert" in output
    assert "elevation" in output


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
            "--start",
            "1000m",
            "--end",
            "1000m",
        ],
        out=buf,
    )
    _assert_raw_xml(buf, "Trimmed")


def test_cmd_trim_time_mode(tmp_path):
    """Test trim with --time flag."""
    path = tmp_path / "input.gpx"
    create_gpx_file(path, [Point(40.0 + i, -74.0, time=i * 60) for i in range(5)])

    buf = StringIO()
    main(["trim", str(path), "-o", "-", "--start", "60s", "--end=1%"], out=buf)
    _assert_raw_xml(buf)


def test_cmd_trim_stdin(tmp_path):
    """Test trim reading from stdin."""
    gpx_path = tmp_path / "input.gpx"
    out_path = tmp_path / "trimmed.gpx"
    create_gpx_file(gpx_path, [Point(40.0 + i, -74.0) for i in range(5)])

    buf = StringIO()
    main(
        ["trim", "-", "-o", str(out_path), "--start=20%", "--end=1"],
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


@no_np_warn()
def test_cmd_elevation(tmp_path):
    """Test elevation subcommand: add elevation to GPX from a DEM file."""
    input_path = tmp_path / "input.gpx"
    create_gpx_file(
        input_path, [Point(48.8, 2.2), Point(48.85, 2.25), Point(48.9, 2.3)]
    )
    dem_path = tmp_path / "dem.tif"
    create_tif_grid(dem_path, 2.1, 48.75, 2.4, 48.95, 125.0)
    out_path = tmp_path / "elevated.gpx"

    buf = StringIO()
    main(["elevation", str(input_path), str(dem_path), "-o", str(out_path)], out=buf)
    output = buf.getvalue()
    assert "Added elevation to" in output
    assert "Updated: 3 point(s)" in output

    gpx = GPX(out_path)
    points = list(gpx.points())
    for pt in points:
        assert pt.elevation is not None
        assert 120 < pt.elevation < 130


def test_cmd_elevation_overwrite_and_stdout(tmp_path):
    """Test elevation --overwrite flag, stdin input, and stdout output."""
    input_path = tmp_path / "input.gpx"
    create_gpx_file(input_path, [Point(48.8, 2.2, 10.0), Point(48.85, 2.25, 20.0)])
    ref_path = tmp_path / "ref.gpx"
    create_gpx_file(ref_path, [Point(48.8, 2.2, 100.0), Point(48.85, 2.25, 200.0)])

    buf1 = StringIO()
    main(["elevation", "-", str(ref_path)], out=buf1, stdin=_file_to_stdin(input_path))
    gpx1 = GPX(BytesIO(buf1.getvalue().encode()))
    assert gpx1.stats().min_elev == 10.0

    buf2 = StringIO()
    main(
        ["elevation", "-", str(ref_path), "--overwrite"],
        out=buf2,
        stdin=_file_to_stdin(input_path),
    )
    assert "<?xml" in buf2.getvalue()
    gpx2 = GPX(BytesIO(buf2.getvalue().encode()))
    assert gpx2.stats().min_elev == 100.0


def test_cmd_fill(tmp_path):
    """Test fill subcommand: fill gaps using reference GPX."""
    input_path = tmp_path / "input.gpx"
    create_gpx_file(
        input_path,
        [Point(48.8, 2.2, time=0), Point(48.86, 2.3, time=10)],
        [Point(50.0, 1.0, time=3600), Point(50.5, 0.5, time=3610)],
    )
    ref_path = tmp_path / "ref.gpx"
    create_gpx_file(
        ref_path,
        [Point(48.8, 2.2), Point(49.0, 2.0), Point(49.5, 1.5), Point(50.0, 1.0)],
    )

    buf = StringIO()
    main(["fill", str(input_path), str(ref_path), "-o", "-"], out=buf)
    gpx = GPX(BytesIO(buf.getvalue().encode()))
    assert len(list(gpx.points())) == 8


def test_cmd_fill_list(tmp_path):
    """Test fill --list outputs gap information."""
    input_path = tmp_path / "input.gpx"
    create_gpx_file(
        input_path,
        [Point(48.8, 2.2, time=0)],
        [Point(51.5, -0.1, time=3600)],
        [Point(40.7, -74.0, time=7200)],
    )
    ref_path = tmp_path / "ref.gpx"
    create_gpx_file(ref_path, [Point(48.8, 2.2), Point(51.5, -0.1), Point(40.7, -74.0)])

    buf = StringIO()
    main(["fill", str(input_path), str(ref_path), "--list"], out=buf)
    output = buf.getvalue()

    assert "dist=" in output
    assert "duration=" in output
    assert "→" in output
    gap_lines = [l for l in output.strip().split("\n") if l]
    assert len(gap_lines) == 2


def test_cmd_fill_selective(tmp_path):
    """Test fill with -g to fill specific gaps."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path,
        *[
            [Point(51.5, -0.1, time=i)] if i % 2 == 0 else [Point(40.7, -74.0, time=i)]
            for i in range(7)
        ],
    )
    ref_path = tmp_path / "ref.gpx"
    create_gpx_file(
        ref_path,
        [Point(40.7, -74.0), Point(42.8, -53.0), Point(48.8, 12.2), Point(51.5, -0.1)],
    )
    out_path = tmp_path / "filled.gpx"

    buf = StringIO()
    main(
        ["fill", "-", str(ref_path), "-o", str(out_path), "-g", "1", "-g", "2", "3"],
        out=buf,
        stdin=_file_to_stdin(gpx_path),
    )
    assert "Filled 3 gap(s)" in buf.getvalue()


def test_cmd_clean(tmp_path):
    """Test clean subcommand: remove empty segments and update bounds."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path,
        [
            Point(48.8, 2.2),
            Point(48.8001, 2.2001),
            Point(48.8002, 2.2002),
            Point(48.85, 2.3),
        ],
    )
    out_path = tmp_path / "cleaned.gpx"

    buf = StringIO()
    main(["clean", str(gpx_path), "-o", str(out_path), "--bounds"], out=buf)
    assert "Cleaned" in buf.getvalue()
    assert len(list(GPX(out_path).points())) == 4
    buf = StringIO()
    main(
        ["clean", "-", "--outliers", "--max-time=inf"],
        out=buf,
        stdin=_file_to_stdin(out_path),
    )
    out = buf.getvalue()
    assert len(out.split("trkpt")) == 4  # one outlier removed


def test_cmd_meta(tmp_path):
    """Test meta subcommand: set metadata fields."""
    gpx = tmp_path / "input.gpx"
    create_gpx_file(gpx, metadata=GPXMetadata(name="A", email="B", copyright="E"))
    out = str(tmp_path / "meta.gpx")

    buf = StringIO()
    main(
        [
            "meta",
            str(gpx),
            "-o",
            out,
            "--name",
            "C",
            "--author",
            "D",
            "--email",
            "",
            "--keywords=F",
        ],
        out=buf,
    )
    assert "Updated metadata" in buf.getvalue()
    assert "Name: C" in buf.getvalue()
    meta = GPX(out).metadata()
    assert meta.author == "D"
    assert meta.email == None
