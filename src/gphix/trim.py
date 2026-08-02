import itertools

from gphix.gpx import GPX, GPXPoint
from gphix.utils import distance


def trim(
    gpx: GPX,
    start: float = 0.0,
    end: float = 0.0,
    by_time: bool = False,
    by_distance: bool = False,
):
    """Trim points from the start and end.

    Tracks are sorted temporally (by earliest timestamp).
    Only points falling inside the middle are retained.

    Args:
        gpx:       GPX to trim.
        start:     Fraction (0.0–1.0) to remove from the beginning.
        end:       Fraction (0.0–1.0) to remove from the end.
        by_time:       If True, *start*/*end* are seconds.
        by_distance:   If True, *start*/*end* are metres.
                        Otherwise they are fractions of total points (0.0–1.0).
    """
    if by_time and by_distance:
        raise ValueError("Cannot specify both by_time and by_distance")

    segments = gpx.segments()
    if not segments:
        return gpx

    counter: float | int = 0.0
    if by_time:
        step = _step_time
    elif by_distance:
        step = _step_dist
    else:
        counter = -1
        step = lambda p1, p2: 1

    positions = []
    for seg in segments:
        first = seg.first_point()
        if first is not None:
            if not by_time and not by_distance:
                counter += 1
            positions.append((seg, first, counter))
        for p1, p2 in itertools.pairwise(seg.points()):
            counter += step(p1, p2)
            positions.append((seg, p2, counter))

    if counter == 0:
        return gpx

    if not by_time and not by_distance:
        start = round(start * (counter + 1))
        end = round(end * counter)

    if start + end >= counter:
        raise ValueError("Cannot remove more points than available")
    end = counter - end
    for seg, pt, pos in positions:
        if not (start <= pos <= end):
            seg.remove(pt)


def _step_time(p1: GPXPoint, p2: GPXPoint) -> float | int:
    if (t1 := p1.time) is not None and (t2 := p2.time) is not None:
        return (t2 - t1).total_seconds()
    else:
        return 0.0


def _step_dist(p1: GPXPoint, p2: GPXPoint) -> float | int:
    return distance(
        (
            (p1.latitude, p1.longitude, p1.elevation),
            (p2.latitude, p2.longitude, p2.elevation),
        )
    )
