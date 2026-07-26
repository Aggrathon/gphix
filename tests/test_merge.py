from gphix.gpx import GPX

from .utils import Point, create_gpx_file


def test_merge_tracks(tmp_path):
    """Test that tracks from multiple files are preserved."""
    f1 = tmp_path / "a.gpx"
    f2 = tmp_path / "b.gpx"
    f3 = tmp_path / "c.gpx"

    create_gpx_file(f1, [Point(40.0, -74.0)])
    create_gpx_file(f2, [Point(41.0, -73.0)])
    create_gpx_file(f3, [Point(50.0, 1.0)])

    merged = GPX.merge([f1, f2, f3])
    assert len(merged.root.findall("gpx:trk", merged.namespaces)) == 3
    assert len(list(merged.points())) == 3


def test_merge_multi_track_files(tmp_path):
    """Test merging files that each contain multiple tracks."""
    f1 = tmp_path / "gpx1.gpx"
    f2 = tmp_path / "gpx2.gpx"

    create_gpx_file(
        f1,
        [Point(40.0, -74.0), Point(40.1, -73.9)],
        [Point(41.0, -73.0), Point(41.1, -72.9)],
    )
    create_gpx_file(
        f2,
        [Point(50.0, 1.0), Point(50.1, 1.1)],
        [Point(51.0, 2.0), Point(51.1, 2.1)],
    )

    merged = GPX.merge([f1, f2])
    assert len(merged.root.findall("gpx:trk", merged.namespaces)) == 4
    assert len(list(merged.points())) == 8


def test_merge_waypoints(tmp_path):
    """Test that waypoints from multiple sources are combined."""
    f1 = tmp_path / "gpx1.gpx"
    f2 = tmp_path / "gpx2.gpx"

    create_gpx_file(f1, [], waypoints=[Point(50.0, 1.0, ele=50.0)])
    create_gpx_file(f2, [], waypoints=[Point(51.0, 2.0), Point(52.0, 3.0, ele=100.0)])

    merged = GPX.merge([f1, f2])
    assert len(list(merged.points())) == 3


def test_merge_metadata(tmp_path):
    """Test that only the first file's metadata is preserved."""
    f1 = tmp_path / "gpx1.gpx"
    f2 = tmp_path / "gpx2.gpx"

    create_gpx_file(f1, [Point(40.0, -74.0)], metadata="<name>First</name>")
    create_gpx_file(f2, [Point(51.0, 1.0)], metadata="<name>Second</name>")

    merged = GPX.merge([f1, f2])
    metas = list(merged.root.findall("gpx:metadata", merged.namespaces))
    assert len(metas) == 1
    name = metas[0].find("gpx:name", merged.namespaces)
    assert name is not None
    assert name.text == "First"


def test_merge_single_file(tmp_path):
    """Merging one file returns an equivalent GPX."""
    f = tmp_path / "input.gpx"
    create_gpx_file(
        f, [Point(48.5, 2.2, 10.0), Point(51.0, -0.8, 20.0), Point(40.1, -74.6, 30.0)]
    )

    orig = GPX(f)
    merged = GPX.merge([f])
    assert merged.stats() == orig.stats()
