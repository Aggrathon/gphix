from datetime import UTC, datetime, timedelta

from gphix.gpx import GPX, GPXMetadata

from .utils import Point, create_gpx, create_gpx_file


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
    assert stats.min_elev is None
    assert stats.max_elev is None
    assert stats.tracks == 1
    assert gpx.metadata() is None


def test_stats_with_elevation(tmp_path):
    """Test stats with a list of custom elevation values."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path,
        [
            Point(48.8584, 2.2945, 0.0),
            Point(51.5074, -0.1278, 50.0),
            Point(40.7128, -74.006, 200.0),
        ],
    )
    gpx = GPX(gpx_path)
    stats = gpx.stats()

    assert stats.min_elev == 0.0
    assert stats.max_elev == 200.0


def test_stats_multi_track(tmp_path):
    """Test that stats correctly aggregate across multiple tracks."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path,
        [Point(40.0, -74.0), Point(40.1, -73.9)],
        [Point(41.0, -73.0), Point(41.1, -72.9)],
    )
    gpx = GPX(gpx_path)
    stats = gpx.stats()

    assert stats.points == 4
    assert stats.tracks == 2
    assert isinstance(stats.distance, float)
    assert stats.duration == 0.0


def test_stats_with_time(tmp_path):
    """Test stats with time data present."""
    base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(
        gpx_path,
        [
            Point(48.8, 2.2, time=0),
            Point(51.5, -0.1, time=300),
            Point(40.7, -74.6, time=600),
        ],
        base_time=base,
    )
    gpx = GPX(gpx_path)
    stats = gpx.stats()
    assert stats.duration == 600
    assert stats.start_time == base
    assert stats.end_time == base + timedelta(seconds=600)


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

    create_gpx_file(
        input_gpx,
        [Point(48.8, 2.9, 100.0), Point(51.5, -0.8, 100.0), Point(40.7, -74.6, 100.0)],
    )
    gpx = GPX(input_gpx)
    points = list(gpx.points())
    assert len(points) == 3
    assert gpx.root.get("creator") == "GPhiX_test"

    for point in points:
        assert point.elevation == 100.0

    assert abs(points[0].latitude - 48.8) < 0.0001
    assert abs(points[0].longitude - 2.9) < 0.0001

    assert abs(points[1].latitude - 51.5) < 0.0001
    assert abs(points[1].longitude - (-0.8)) < 0.0001

    assert abs(points[2].latitude - 40.7) < 0.0001
    assert abs(points[2].longitude - (-74.6)) < 0.0001

    gpx.write(output_gpx)
    gpx2 = GPX(output_gpx)
    assert gpx2.root.get("creator") == "GPhiX"
    assert gpx2.to_string() == gpx.to_string()


def test_segments_sort_by_geographic_gap(tmp_path):
    """Time-less segments are bridged into geographic gaps."""
    gpx_path = tmp_path / "gap_fill.gpx"
    create_gpx_file(
        gpx_path,
        [Point(10.0, 20.0, time=0)],
        [Point(30.0, 40.0, time=3600)],
        [Point(50.0, 60.0, time=7200)],
    )

    gpx = GPX(gpx_path)
    lats = [p.latitude for s in gpx.segments() if (p := s.first_point())]
    assert lats == [10.0, 30.0, 50.0]

    gpx.add_track((20.0, 30.0), (25.0, 30.0))
    lats = [p.latitude for s in gpx.segments(True) if (p := s.first_point())]
    assert lats == [10.0, 20.0, 30.0, 50.0]

    gpx.add_track()
    assert len(gpx.segments()) == 4

    gpx.add_track((25.0, 35.0), (30.0, 35.0))
    lats = [p.latitude for s in gpx.segments(True) if (p := s.first_point())]
    assert lats == [10.0, 20.0, 25.0, 30.0, 50.0]

    create_gpx_file(
        gpx_path, [Point(10.0, 20.0)], [Point(30.0, 40.0)], [Point(50.0, 60.0)]
    )
    gpx = GPX(gpx_path)
    lats = [p.latitude for s in gpx.segments(True) if (p := s.first_point())]
    assert lats == [10.0, 30.0, 50.0]


def test_track_builder(tmp_path):
    """Test TrackBuilder and GPXPoint setters."""
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    gpx = GPX(None)
    gpx.add_track((1.0, 2.0), (3.0, 4.0))
    gpx.add_track((5.0, 6.0, 123.4, base))
    gpx.add_waypoint(7.0, 8.0).elevation = 99.0

    output = tmp_path / "builder.gpx"
    gpx.write(output)
    gpx2 = GPX(output)

    assert len(gpx2.root.findall("gpx:trk", gpx2.namespaces)) == 2
    points = list(gpx2.points())
    assert len(points) == 4

    assert points[1].elevation is None
    assert points[2].elevation == 123.4
    assert points[2].time == base
    assert points[3].elevation == 99.0


def test_metadata_empty(tmp_path):
    """Test metadata() returns None when no <metadata> element exists."""
    gpx_path = tmp_path / "input.gpx"
    create_gpx_file(gpx_path)
    gpx = GPX(gpx_path)
    assert gpx.metadata() is None


def test_metadata_full(tmp_path):
    """Test parsing a GPX file with full metadata."""
    gpx_path = tmp_path / "input.gpx"
    meta = GPXMetadata(
        name="My Trip",
        description="A weekend hike",
        author="Alice",
        email="alice@example.com",
        copyright="CC-BY 2024",
        links=(("https://example.com/trip", "Trip Page", "text/html"),),
        time=datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC),
        keywords="hiking, summer",
        min_lat=40.0,
        max_lat=52.0,
        min_lon=-75.0,
        max_lon=3.0,
    )
    create_gpx_file(gpx_path, metadata=meta)
    gpx = GPX(gpx_path)
    assert meta == gpx.metadata()
    gpx = create_gpx(metadata=meta)
    assert meta == gpx.metadata()
    meta.name = "B"
    meta.email = None
    gpx.set_metadata(meta)
    assert meta == gpx.metadata()


def test_clean():
    gpx = create_gpx([], [Point(1.0, 1.0), (Point(-1.0, 2.0))], [])
    gpx.clean()
    stats = gpx.stats()
    assert stats.points == 2
    assert len(gpx.segments()) == 1
    assert stats.tracks == 1
    assert gpx.metadata() is None
    gpx.clean(add_bounds=True)
    assert (meta := gpx.metadata())
    assert meta.min_lat == -1.0
    assert meta.max_lat == 1.0
    assert meta.min_lon == 1.0
    assert meta.max_lon == 2.0
    assert meta.time is None
    time = datetime.now(UTC)
    gpx.add_track((1.0, 3.0, None, time))
    gpx.clean()
    assert (meta := gpx.metadata())
    assert meta.max_lon == 3.0
    assert meta.time is None
    gpx.add_track((1.0, 1.0), (0.9999, 1.0), (-0.1, 1.0), (0.9998, 1.0), (0.9997, 1.0))
    assert len(gpx.segments()[-1]) == 5
    gpx.clean(outliers=True, add_bounds=True)
    assert len(gpx.segments()[-1]) == 4
    assert gpx.metadata().time == time
    seg = gpx.add_track().add_segment()
    for i in [-11, 202, 203, 204, 205, 406, 507, 508, 509, 510, 511, 612]:
        seg.add_point(1.0, 1.0, time=time + timedelta(seconds=i))
    assert len(gpx.segments()[-1]) == 12
    gpx.clean(outliers=True, max_time=50, min_size=2)
    assert len(gpx.segments()[-1]) == 9
    assert gpx.metadata().time > time


def test_clean_merge_tracks():
    gpx = create_gpx(
        (Point(1.0, 1.0), Point(2.0, 2.0)),
        (Point(1.0, 1.0, time=600),),
        (Point(2.0, 2.0, time=100),),
        (Point(3.0, 3.0, time=300),),
        waypoints=[Point(5.0, 5.0)],
    )
    gpx.tracks()[0].name = "first"
    gpx.clean(merge_tracks=True)
    assert len(gpx.segments()) == 4
    assert len(gpx.tracks()) == 1
    assert gpx.tracks()[0].name == "first"
    assert len(list(gpx.points())) == 6
    assert list(gpx.waypoints())
    assert [p.latitude for p in gpx.points()] == [1.0, 2.0, 2.0, 3.0, 1.0, 5.0]


def test_track_metadata():
    """Test GPX.add_track() accepts name, description, and track_type kwargs."""
    gpx = GPX(None)
    track = gpx.add_track(
        name="Morning Run",
        description="A sunrise jog",
        track_type="run",
    )
    gpx.add_track(name="Second")
    gpx.add_track()
    assert track.name == "Morning Run"
    assert track.description == "A sunrise jog"
    assert track.track_type == "run"
    track.name = "Test Track"
    track.description = "A test"
    track.track_type = "hike"
    track = gpx.tracks()[0]
    assert track.name == "Test Track"
    assert track.description == "A test"
    assert track.track_type == "hike"
    assert gpx.tracks()[1].name == "Second"
    assert gpx.tracks()[2].name == None
    track.name = None
    track.description = ""
    track.track_type = None
    assert track.name is None
    assert track.description is None
    assert track.track_type is None


def test_gpstrack_add_segment():
    """Test GPXTrack.add_segment() creates a trkseg and returns GPXSegment."""
    gpx = GPX(None)
    track = gpx.add_track()
    track.add_segment((1.0, 2.0), (3.0, 4.0))
    assert len(list(track.add_segment().points())) == 0
    t2 = gpx.add_track()
    s2 = t2.add_segment((5.0, 6.0))
    assert len(list(s2.points())) == 1
    assert len(gpx.tracks()) == 2
    assert len(list(gpx.points())) == 3
