from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Iterator
from math import radians
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparisonT

EARTH_RADIUS_M = 6371000.0
METERS_PER_DEG = 111320.0


class LocalKDTree:
    """KDTree over lat/lon points projected to a local equirectangular meter grid.

    The tree stores points projected from (lat, lon) to (x, y) meters
    relative to the mean center of all points, so query distances are
    meaningful in metres.  Both the index and queries share the same
    projection reference (the global average lat/lon).
    """

    def __init__(self, points: Iterable[tuple[float, float]]) -> None:
        import numpy as np
        from scipy.spatial import KDTree

        pts = np.asarray([list(p) for p in points], dtype=float)
        assert pts.size > 0
        avg_lat = np.mean(pts[:, 0])
        avg_lon = np.mean(pts[:, 1])
        x = (pts[:, 1] - avg_lon) * math.cos(math.radians(avg_lat)) * METERS_PER_DEG
        y = (pts[:, 0] - avg_lat) * METERS_PER_DEG

        self._tree = KDTree(np.stack([x, y], -1))
        self._n = len(pts)
        self._avg_lat = avg_lat
        self._avg_lon = avg_lon
        self._ref_met = math.cos(math.radians(avg_lat)) * METERS_PER_DEG

    def _project(self, lat: float, lon: float) -> tuple[float, float]:
        """Project (lat, lon) into the tree's local meter grid."""
        x = (lon - self._avg_lon) * self._ref_met
        y = (lat - self._avg_lat) * METERS_PER_DEG
        return x, y

    def query(self, lat: float, lon: float) -> int:
        """Return the index of the nearest point."""
        return self._tree.query(self._project(lat, lon))[1]

    def query_ball_point(self, lat: float, lon: float, r: float) -> list[int]:
        """Return indices of points within *r* metres."""
        return self._tree.query_ball_point(self._project(lat, lon), r=r, workers=-1)


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


def cum_distance(
    coords: Iterable[tuple[float, float, float | None]],
) -> Iterator[float]:
    """Generate the cumulative 3D distance in meters for a sequence of points."""
    total = 0.0
    yield total
    for (lat1, lon1, elev1), (lat2, lon2, elev2) in itertools.pairwise(coords):
        ground = haversine(lat1, lon1, lat2, lon2)
        if elev2 is not None and elev1 is not None:
            total += math.hypot(ground, elev2 - elev1)
        else:
            total += ground
        yield total


def update_bounds(
    minv: SupportsRichComparisonT | None,
    maxv: SupportsRichComparisonT | None,
    values: Iterable[SupportsRichComparisonT],
) -> tuple[SupportsRichComparisonT | None, SupportsRichComparisonT | None]:
    if values:
        maxv = max(max(values), maxv) if maxv is not None else max(values)
        minv = min(min(values), minv) if minv is not None else min(values)
    return minv, maxv


def project_to_edge(
    p1: tuple[float, float, float | None],
    p2: tuple[float, float, float | None],
    pt: tuple[float, float],
) -> tuple[float, float, float | None]:
    """Return the closest point on segment p1-p2 to point pt, with interpolated elevation."""
    x1, y1, e1 = p1
    x2, y2, e2 = p2
    x, y = pt
    dx, dy = x2 - x1, y2 - y1
    denom = dx * dx + dy * dy
    if denom == 0.0:
        return x1, y1, e1
    t = ((x - x1) * dx + (y - y1) * dy) / denom
    t = max(0.0, min(1.0, t))
    e = (e1 + t * (e2 - e1)) if e1 is not None and e2 is not None else None
    return (x1 + t * dx, y1 + t * dy, e)


def last[T](iterator: Iterator[T] | Iterable[T]) -> None | T:
    """Return the last item of an iterator."""
    item = None
    for i in iterator:
        item = i
    return item


def flatten[T](nested: list[T | list[T]] | None) -> list[T] | None:
    """Flatten a list potentially containing lists."""
    if nested is None:
        return None
    flat = []
    for i in nested:
        if isinstance(i, list):
            flat.extend(i)
        else:
            flat.append(i)
    return flat
