import itertools
import math
from collections.abc import Iterable
from math import radians

_EARTH_RADIUS_M = 6371000


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in meters between two points."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return _EARTH_RADIUS_M * c


def distance(coords: Iterable[tuple[float, float, float | None]]) -> float:
    """Return the total 3D distance in meters for a sequence of points.

    Each coordinate is a (lat, lon, elevation) tuple.
    Omit elevation (use None) for 2D distance.
    """
    total = 0.0
    for (lat1, lon1, elev1), (lat2, lon2, elev2) in itertools.pairwise(coords):
        ground = haversine(lat1, lon1, lat2, lon2)
        if elev2 is not None and elev1 is not None:
            total += math.hypot(ground, elev2 - elev1)
        else:
            total += ground
    return total
