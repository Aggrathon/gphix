from gphix.gpx import GPX

from .utils import create_gpx_file


def test_gpx_class_parse(tmp_path):
    """Test the GPX class for parsing GPX files."""
    input_gpx = tmp_path / "input.gpx"
    output_gpx = tmp_path / "output.gpx"

    create_gpx_file(str(input_gpx), with_elevation=True)
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

    # Test writing with GPX class
    gpx.write(str(output_gpx))
    gpx2 = GPX(output_gpx)
    points2 = list(gpx2.points())
    assert len(points2) == 3
