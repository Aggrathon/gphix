from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Sequence
from math import radians
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparisonT

EARTH_RADIUS_M = 6371000.0
METERS_PER_DEG = 111320.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in meters between two points."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_M * c


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


def update_bounds(
    minv: SupportsRichComparisonT | None,
    maxv: SupportsRichComparisonT | None,
    values: Sequence[SupportsRichComparisonT],
) -> tuple[SupportsRichComparisonT | None, SupportsRichComparisonT | None]:
    if values:
        maxv = max(max(values), maxv) if maxv is not None else max(values)
        minv = min(min(values), minv) if minv is not None else min(values)
    return minv, maxv
