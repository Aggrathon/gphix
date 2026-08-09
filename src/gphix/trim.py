import itertools
from typing import Literal

from gphix.gpx import GPX, GPXSegment
from gphix.utils import distance

UNITS = Literal["i", "index", "m", "distance", "s", "time", "p", "percent"]


def trim(
    gpx: GPX,
    start: float | tuple[int, int] = 0,
    start_unit: UNITS = "i",
    end: float | tuple[int, int] = 0,
    end_unit: UNITS = "i",
):
    """Trim points from the start and end.

    Tracks are sorted temporally (by earliest timestamp).
    Only points falling inside the middle are retained.

    Args:
        gpx:       GPX to trim.
        start:     Amount to remove from the beginning (or (segment, index) of first point to keep).
        start_unit: Unit — `index`/`i` (points), `distance`/`m` (metres), `time`/`s` (seconds), `percent`/`p` (fraction of total points).
        end:       Amount to remove from the end (or (segment, index) of last point to keep).
        end_unit:  Same units as `start_unit`.
    """

    segments = gpx.segments(True)
    if not segments:
        return

    if isinstance(start, (tuple, list)):
        start_seg, start_idx = start
    else:
        start_seg, start_idx = _find_cut_idx(segments, start, start_unit, False)
    if isinstance(end, (tuple, list)):
        end_seg, end_idx = end
    else:
        end_seg, end_idx = _find_cut_idx(segments, end, end_unit, True)

    if start_seg > end_seg or (start_seg == end_seg and start_idx > end_idx):
        raise ValueError("Cannot trim when start is after end")

    for seg in segments[end_seg + 1 :]:
        seg.remove(None)
    seg = segments[end_seg]
    for pt in list(itertools.islice(seg.points(), end_idx + 1, None)):
        seg.remove(pt)

    for seg in segments[:start_seg]:
        seg.remove(None)
    seg = segments[start_seg]
    for pt in list(itertools.islice(seg.points(), start_idx)):
        seg.remove(pt)


def _find_cut_idx(
    segments: list[GPXSegment], value: float, unit: UNITS, reverse: bool
) -> tuple[int, int]:
    if value == 0:
        if reverse:
            return len(segments) - 1, len(segments[-1]) - 1
        return 0, 0

    # percent → index (value is 0.0–1.0 fraction)
    if unit in ("p", "percent"):
        total = sum(len(s) for s in segments)
        unit = "i"
        value = round(value * total)

    if unit in ("i", "index"):
        return _cut_index(segments, int(value), reverse)
    elif unit in ("m", "distance"):
        return _cut_distance(segments, float(value), reverse)
    elif unit in ("s", "time"):
        return _cut_time(segments, float(value), reverse)
    raise ValueError("Unknown unit: " + unit)


def _cut_index(segments: list[GPXSegment], value: int, reverse: bool):
    if reverse:
        for i, seg in enumerate(reversed(segments)):
            if value < len(seg):
                return len(segments) - i - 1, len(seg) - value - 1
            value -= len(seg)
    else:
        for i, seg in enumerate(segments):
            if value < len(seg):
                return i, value
            value -= len(seg)
    raise IndexError()


def _cut_distance(segments: list[GPXSegment], value: float, reverse: bool):
    dist = 0.0
    if reverse:
        pt = segments[-1].last_point()
        last = (pt.latitude, pt.longitude, pt.elevation)  # type: ignore
        for i, seg in enumerate(reversed(segments)):
            for j, pt in enumerate(reversed(list(seg.points()))):
                nxt = (pt.latitude, pt.longitude, pt.elevation)
                dist += distance((nxt, last))
                if dist > value:
                    return len(segments) - i - 1, len(seg) - j - 1
                last = nxt
    else:
        pt = segments[0].first_point()
        first = (pt.latitude, pt.longitude, pt.elevation)  # type: ignore
        for i, seg in enumerate(segments):
            for j, pt in enumerate(seg.points()):
                nxt = (pt.latitude, pt.longitude, pt.elevation)
                dist += distance((first, nxt))
                if dist > value:
                    return i, j
                first = nxt
    raise IndexError()


def _cut_time(segments: list[GPXSegment], value: float, reverse: bool):
    if reverse:
        last = None
        for i, seg in enumerate(reversed(segments)):
            for j, pt in enumerate(reversed(list(seg.points()))):
                if (t := pt.time) is not None:
                    if last:
                        if (last - t).total_seconds() >= value:
                            return len(segments) - i - 1, len(seg) - j - 1
                    else:
                        last = t
    else:
        first = None
        for i, seg in enumerate(segments):
            for j, pt in enumerate(seg.points()):
                if (t := pt.time) is not None:
                    if first:
                        if (t - first).total_seconds() >= value:
                            return i, j
                    else:
                        first = t
    raise IndexError()
