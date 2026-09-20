"""Fuse attributes from source GPX files into a base GPX using DTW offset estimation."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from typing import TYPE_CHECKING

from gphix.gpx import GPX
from gphix.utils import EARTH_RADIUS_M

if TYPE_CHECKING:
    from numpy import ndarray


def _dtw_distance_matrix(latlon1: ndarray, latlon2: ndarray) -> ndarray:
    """Compute pairwise haversine distance matrix between base and source points."""
    import numpy as np

    bla = np.radians(latlon1[:, 0])
    blo = np.radians(latlon1[:, 1])
    sla = np.radians(latlon2[:, 0])
    slo = np.radians(latlon2[:, 1])

    cos_b = np.cos(bla)  # (n,)
    sin_b = np.sin(bla)
    cos_s = np.cos(sla)
    sin_s = np.sin(sla)

    cos_dl = np.cos(blo[:, None] - slo[None, :])  # (n, m)
    dot = sin_b[:, None] * sin_s[None, :] + cos_b[:, None] * cos_s[None, :] * cos_dl
    dot = np.clip(dot, -1.0, 1.0)
    dist = EARTH_RADIUS_M * np.arccos(dot)
    return dist


def match_dtw(latlon1: ndarray, latlon2: ndarray) -> Iterator[tuple[int, int]]:
    """Compute DTW alignment and return the closest one-to-one matches on the optimal path."""
    import numpy as np

    dist_matrix = _dtw_distance_matrix(latlon1, latlon2)
    n, m = dist_matrix.shape
    # Accumulated cost matrix
    acc = np.full((n + 1, m + 1), np.inf)
    acc[0, 0] = 0.0
    # Backpointer: 0=up, 1=diagonal, 2=left
    bp = np.zeros((n, m), dtype=np.int8)

    for i in range(n):
        for j in range(m):
            c = dist_matrix[i, j]
            candidates = [acc[i, j + 1] + c, acc[i, j] + c, acc[i + 1, j] + c]
            best = np.argmin(candidates)
            acc[i + 1, j + 1] = candidates[best]
            bp[i, j] = best

    # Backtrack
    jfi = [-1] * n
    ifj = [-1] * m
    i, j = int(n - 1), int(m - 1)
    while i >= 0 and j >= 0:
        step = bp[i, j]
        if jfi[i] < 0 or dist_matrix[i, j] < dist_matrix[i, jfi[i]]:
            jfi[i] = j
        if ifj[j] < 0 or dist_matrix[i, j] < dist_matrix[ifj[j], j]:
            ifj[j] = i
        i -= step < 2
        j -= step > 0
    # Yield only the closest matches
    if n < m:
        for i, j in enumerate(jfi):
            if ifj[j] == i:
                yield i, j
    else:
        for j, i in enumerate(ifj):
            if jfi[i] == j:
                yield i, j


def _nearest_idx(insert: int, value: float, arr: ndarray) -> int:
    if insert == 0:
        return 0
    if insert >= len(arr):
        return insert - 1
    w1, w2 = arr[insert - 1 : insert + 1]
    if value - w1 < w2 - value:
        return insert - 1
    return insert


def match_nearest(a: ndarray, b: ndarray) -> Iterator[tuple[int, int]]:
    """Find matching pairs in sorted arrays."""
    if len(b) < len(a):
        for j, i in match_nearest(b, a):
            yield i, j

    for i, j in enumerate(b.searchsorted(a)):
        j = _nearest_idx(j, a[i], b)
        k = _nearest_idx(a.searchsorted(b[j]), b[j], a)
        if k == i:
            yield i, j


def suggest_offset(base: GPX, source: GPX) -> tuple[float, float]:
    """Estimate the time offset between base and source GPX files using DTW.

    Computes DTW alignment between the first segment of each file based on
    GPS coordinates, then extracts time deltas from the optimal path.

    Args:
        base: Base GPX (coordinates from this).
        source: Source GPX (attributes from this).

    Returns:
        ``(median_offset_seconds, median_residual_seconds)`` where positive
        offset means the source clock leads the base clock.

    Raises:
        ValueError: If either file has no segments or no time data.
    """
    base_segs = base.segments()
    source_segs = source.segments()
    if not base_segs or not source_segs:
        raise ValueError("Both GPX files must have at least one segment")

    base_points = [
        [pt.latitude, pt.longitude, time.timestamp()]
        for pt in base_segs[0].points()
        if (time := pt.time)
    ]
    source_points = [
        [pt.latitude, pt.longitude, time.timestamp()]
        for pt in source_segs[0].points()
        if (time := pt.time)
    ]

    if len(base_points) < 2 or len(source_points) < 2:
        raise ValueError("Both tracks must have at least 2 points")

    import numpy as np

    base_coords = np.array(base_points)
    source_coords = np.array(source_points)

    # Compute DTW
    path = list(match_dtw(base_coords[:, :2], source_coords[:, :2]))
    offset = np.array([source_coords[j, 2] - base_coords[i, 2] for i, j in path])
    if len(offset) < 2:
        raise ValueError("The match must have at least 2 points")
    median_offset = np.median(offset)
    median_residual = np.median(np.abs(offset - median_offset))
    return float(median_offset), float(median_residual)


def fuse_segments(
    base: GPX, source: GPX, offset: float = 0.0, max_time: float = 20.0
) -> tuple[int, int]:
    """Fuse source attributes into base coordinates using nearest-time matching.

    For each base point, finds the nearest source point within *max_time* seconds
    of base_time. If found and the base point is missing an attribute,
    the source attribute is copied.

    Args:
        base: Base GPX (attributes are copied to here).
        source: Source GPX (attributes are copied from here).
        offset: Time offset in seconds for the source. Positive = source clock leads base clock.
        max_time: Maximum time difference in seconds for a match.
    Returns:
        The number of matched points and copied attributes.
    """
    import numpy as np

    source_pts = [
        (time.timestamp() - offset, pt)
        for pt in source.points(tracks_only=True)
        if (time := pt.time)
    ]
    source_pts.sort(key=lambda x: x[0])
    source_secs = np.array([t for t, _ in source_pts])

    base_pts = [
        (time.timestamp(), pt)
        for pt in base.points(tracks_only=True)
        if (time := pt.time)
    ]
    base_pts.sort(key=lambda x: x[0])
    base_secs = np.array([t for t, _ in base_pts])

    nump = 0
    numa = 0
    for i, j in match_nearest(base_secs, source_secs):
        if abs(base_secs[i] - source_secs[j]) <= max_time:
            nump += 1
            numa += _merge_children(base_pts[i][1].element, source_pts[j][1].element)

    return nump, numa


def _merge_children(parent: ET.Element, source: ET.Element) -> int:
    """Recursively merge *source*'s children into *parent*'s children."""
    num = 0
    for sub in source:
        tag = sub.tag.split("}")[-1]
        node = next((c for c in parent if c.tag.split("}")[-1] == tag), None)
        if node is not None:
            num += _merge_children(node, sub)
        else:
            num += 1
            parent.append(copy.deepcopy(sub))
    return num
