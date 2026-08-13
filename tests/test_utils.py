from gphix.utils import format_distance, format_duration, format_int, last


def test_format_distance():
    # Test _format_distance for values below 1 km.
    assert format_distance(500.0) == "500 m"
    assert format_distance(10.0) == "10 m"
    # Test _format_distance for values >= 1 km.
    assert format_distance(1500.0) == "1.50 km"
    assert format_distance(10500.0) == "10.50 km"


def test_format_duration():
    """Test _format_duration helper."""
    assert format_duration(0) == "0s"
    assert format_duration(45.213) == "45s"
    assert format_duration(65) == "1m 5s"
    assert format_duration(3661.454) == "1h 1m 1s"
    assert format_duration(7265) == "2h 1m 5s"


def test_last():
    assert last(range(3)) == 2
    assert last("asd") == "d"
    assert last([1, "23", 6]) == 6


def test_format_int():
    assert format_int(1_000) == "1000"
    assert format_int(10_000) == "10 000"
    assert format_int(999) == "999"
    assert format_int(777_888_999) == "777 888 999"
