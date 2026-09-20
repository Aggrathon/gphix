"""Helper functions for the Pyodide powered Web UI."""

import itertools
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from gphix.elevation import add_elevation_to_gpx
from gphix.fix import ReferencePaths, fill_gaps, find_frozen, find_gaps, fix_frozen
from gphix.fuse import fuse_segments, suggest_offset
from gphix.gpx import GPX, GPXMetadata
from gphix.trim import trim
from gphix.utils import (
    cum_distance,
    distance,
    format_distance,
    format_duration,
    format_int,
)


@dataclass(slots=True)
class Point:
    """A single point with lat/lon, elevation, time, and cumulative distance."""

    lat: float
    lon: float
    ele: float | None = None
    time: datetime | None = None
    dist: float | None = None

    def to_dict(self) -> dict[str, str | float | None]:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "ele": self.ele,
            "time": self.time.isoformat() if self.time else None,
            "dist": self.dist,
        }

    def coord(self) -> tuple[float, float, float | None]:
        return self.lat, self.lon, self.ele


@dataclass(slots=True)
class AppState:
    """Snapshot of the current application state (loaded GPX, files, computed data)."""

    gpx: GPX
    files: list[str]
    stats: dict[str, str] | None = None
    segments: list[list[Point]] | None = None


current: AppState | None = None
previous: list[AppState] = []


def reset():
    """Discard current state, pushing it onto the undo stack."""
    global current
    if current is not None:
        previous.append(current)
        current = None


def undo() -> bool:
    """Restore the previous state from the undo stack. Returns True if there is a state."""
    global current
    if previous:
        current = previous.pop()
    elif current is not None:
        previous.append(current)
        current = None
    return current is not None


def next(state: AppState):
    """Save the current state (if any) and set a new state."""
    global current
    if current is None:
        previous.clear()
    else:
        previous.append(current)
    current = state


def clone_next(shallow: bool = False) -> GPX | None:
    """Clone the current GPX, apply a state transition, and return the clone.

    Args:
        shallow: If True, reuse stats and segments from the current state.
    """
    if current:
        gpx = deepcopy(current.gpx)
        if shallow:
            next(AppState(gpx, current.files, current.stats, current.segments))
        else:
            next(AppState(gpx, current.files if current else []))
        return gpx


def load_gpx(root: str, paths: list[str]):
    """Load one or more GPX files and merge them into the current state.

    Args:
        root: Base directory for resolving relative paths.
        paths: List of GPX file paths to load.
    """
    dir = Path(root)
    if current is None:
        gpxs = [GPX(dir / p) for p in paths]
    else:
        gpxs = [current.gpx] + [GPX(dir / p) for p in paths]
        paths = current.files + paths
    if len(gpxs) > 1:
        next(AppState(GPX.merge(gpxs), files=paths))
    else:
        next(AppState(gpxs[0], files=paths))


def get_stats() -> dict[str, str]:
    """Compute and return stats (points, tracks, segments, distance, duration, elevation). Cached on first call."""
    if current is None:
        return {}
    if current.stats is None:
        stats = current.gpx.stats()
        current.stats = {
            "Points": format_int(stats.points),
            "Tracks": format_int(stats.tracks),
            "Segments": format_int(len(current.gpx.segments(routes=True))),
            "Distance": format_distance(stats.distance),
            "Duration": format_duration(stats.duration),
        }
        if stats.start_time:
            current.stats["Start"] = stats.start_time.isoformat()
        if stats.end_time:
            current.stats["End"] = stats.end_time.isoformat()
        if stats.min_elev is not None and stats.max_elev is not None:
            current.stats["Elevation"] = (
                f"{stats.min_elev:.0f} - {stats.max_elev:.0f} m"
            )
    return current.stats


def get_metadata() -> dict[str, str | None]:
    """Return parsed metadata from the current GPX file."""
    if current is None:
        return {}
    meta = current.gpx.metadata()
    if not meta:
        return {}
    else:
        return {
            "name": meta.name,
            "description": meta.description,
            "author": meta.author,
            "email": meta.email,
            "copyright": meta.copyright,
            "keywords": meta.keywords,
            "time": meta.time.isoformat() if meta.time else None,
        }


def get_segments() -> list[list[list[float]]]:
    """Return all track/route segments as lists of [lat, lon] coordinates. Cached on first call."""
    if current is None:
        return []
    if current.segments is None:
        current.segments = [
            [Point(p.latitude, p.longitude, p.elevation, p.time) for p in seg.points()]
            for seg in current.gpx.segments(True)
        ]
    return [[[p.lat, p.lon] for p in seg] for seg in current.segments]


def get_plot_data() -> (
    tuple[list[float], list[float | None], list[float | None]] | None
):
    """Return (distance, time, elevation) arrays for plotting. Cached on first call."""
    if current is None:
        return None
    if current.segments is None:
        current.segments = [
            [Point(p.latitude, p.longitude, p.elevation, p.time) for p in seg.points()]
            for seg in current.gpx.segments(True)
        ]
    if current.segments and current.segments[0][0].dist is None:
        pd = 0.0
        last = None
        for seg in current.segments:
            if last is not None:
                pd = last.dist + distance((last.coord(), seg[0].coord()))  # type: ignore
            for d, p in zip(cum_distance(p.coord() for p in seg), seg):
                p.dist = pd + d
            last = seg[-1]
    dist, time, elev = [], [], []
    for seg in current.segments:
        dist.extend(p.dist for p in seg)
        time.extend((p.time.timestamp() if p.time else None) for p in seg)
        elev.extend(p.ele for p in seg)
    return dist, time, elev


def get_point(
    seg_idx: int, pt_idx: int | None = None
) -> dict[str, str | float | None] | None:
    """Return a single point's data. If *pt_idx* is None seg_idx is treated as a flat index."""
    if current is None or current.segments is None:
        return None
    if pt_idx is None:
        if (idx := get_point_idx(seg_idx)) is None:
            return None
        seg_idx, pt_idx = idx
    elif pt_idx < 0:
        seg_idx -= 1
        pt_idx += len(current.segments[seg_idx])
    elif pt_idx >= len(current.segments[seg_idx]):
        pt_idx -= len(current.segments[seg_idx])
        seg_idx += 1
    if seg_idx < 0 or seg_idx >= len(current.segments):
        return None
    return current.segments[seg_idx][pt_idx].to_dict() | {"seg": seg_idx, "idx": pt_idx}


def get_point_idx(idx: int) -> tuple[int, int] | None:
    """Convert a flat point index into (segment_index, point_in_segment)."""
    if current is None or not current.segments:
        return None
    elif idx == 0:
        return 0, 0
    elif idx > 0:
        for i, seg in enumerate(current.segments):
            if idx < len(seg):
                return i, idx
            idx -= len(seg)
    elif idx == -1:
        return len(current.segments) - 1, len(current.segments[-1]) - 1
    return None


def get_files() -> list[str]:
    """Return the list of loaded file paths."""
    if current is None:
        return []
    else:
        return current.files


def get_track_metadata() -> list[dict[str, str | None]]:
    """Return metadata (name, description, type) for each track in the current GPX."""
    if current is None:
        return []
    return [
        {"name": t.name, "description": t.description, "type": t.track_type}
        for t in current.gpx.tracks()
    ]


def set_track_metadata(tracks: list[dict[str, str]]):
    """Set metadata (name, description, type) for each track in the current GPX."""
    if gpx := clone_next(shallow=True):
        for t, meta in zip(gpx.tracks(), tracks):
            t.name = meta.get("name") or None
            t.description = meta.get("description") or None
            t.track_type = meta.get("type") or None


def set_metadata(
    name: str, description: str, author: str, email: str, copyright: str, keywords: str
):
    """Set current GPX metadata fields."""
    if gpx := clone_next(shallow=True):
        meta = gpx.metadata() or GPXMetadata()
        meta.name = name or None
        meta.description = description or None
        meta.author = author or None
        meta.email = email or None
        meta.copyright = copyright or None
        meta.keywords = keywords or None
        gpx.set_metadata(meta)


def trim_before(seg_idx: int, pt_idx: int):
    """Trim everything before the given point in the current GPX."""
    if gpx := clone_next():
        trim(gpx, start=(seg_idx, pt_idx))


def trim_after(seg_idx: int, pt_idx: int):
    """Trim everything after the given point in the current GPX."""
    if gpx := clone_next():
        trim(gpx, end=(seg_idx, pt_idx))


def apply_clean(
    outliers: bool = False,
    max_distance: float = 100.0,
    max_time: float = 70.0,
    min_size: int = 1,
    merge_tracks: bool = False,
    add_bounds: bool = False,
):
    """Clean the current GPX."""
    if gpx := clone_next():
        gpx.clean(outliers, max_distance, max_time, min_size, merge_tracks, add_bounds)


def apply_elevation(
    paths: list[str], radius: float = 50.0, overwrite: bool = False
) -> dict[str, int]:
    """Add elevation data to the current GPX from external sources.

    Returns:
        Dict with key ``points`` (number of points updated).
    """
    points = 0
    if gpx := clone_next():
        points = add_elevation_to_gpx(gpx, paths, overwrite=overwrite, radius=radius)
    return {"points": points}


def find_issues(
    gaps: bool,
    frozen: bool,
    distance: float = 100.0,
    duration: float = 30.0,
    points: int = 3,
) -> list[dict[str, str | float]]:
    """Find gap and frozen-section issues in the current GPX."""
    if current is None:
        return []
    return [
        {
            "distance": format_distance(g.distance),
            "start_lat": g.start.lat,
            "start_lon": g.start.lon,
            "end_lat": g.end.lat,
            "end_lon": g.end.lon,
            "duration": format_duration(g.duration) if g.duration else "",
            "time": g.start.time.isoformat()
            if g.start.time
            else g.end.time.isoformat()
            if g.end.time
            else "",
            "length": len(g.points) if g.points else 0,
        }
        for g in itertools.chain(
            find_gaps(current.gpx, distance, duration) if gaps else (),
            find_frozen(current.gpx, distance, duration, points) if frozen else (),
        )
    ]


def apply_fix(
    ref_path: str | None = None,
    gaps: bool = True,
    frozen: bool = True,
    distance: float = 100.0,
    duration: float = 30.0,
    points: int = 3,
    selected: list[int] | None = None,
):
    """Apply fixes (gap filling and/or frozen section repair) to the current GPX."""
    if gpx := clone_next():
        ref = ReferencePaths(GPX(ref_path) if ref_path else None)
        if gaps and frozen and selected:
            ngaps = len(find_gaps(gpx, distance, duration))
            gsel = [s for s in selected if s < ngaps]
            fsel = [s - ngaps for s in selected if s >= ngaps]
        else:
            gsel = fsel = selected
        if gaps:
            fill_gaps(gpx, ref, distance, duration, gsel)
        if frozen:
            fix_frozen(gpx, ref, distance, duration, points, fsel)


def insert_points(rows: list[dict[str, str | float]]) -> None:
    """Add all rows as a single new track to the current GPX."""
    if gpx := clone_next():
        seg = gpx.add_track().add_segment()
        for row in rows:
            lat = float(row["lat"])
            lon = float(row["lon"])
            ele = row.get("ele")
            time = row.get("time")
            time = datetime.fromisoformat(time) if time else None  # type:ignore
            ele = float(ele) if ele is not None and ele != "" else None
            seg.add_point(lat, lon, ele, time)


def save_gpx() -> str | None:
    """Return the current GPX as an XML string."""
    if current is None:
        return None
    return current.gpx.to_string()


def fuse_gpx(
    source_path: str, offset: float | None = None, max_time: float = 20.0
) -> dict[str, int | float]:
    """Fuse attributes from a source GPX into the current GPX.

    Args:
        source_path: Path to the source GPX file (in the Pyodide FS).
        offset: Time offset in seconds for the source. Pass ``None`` to auto-suggest.
        max_time: Maximum time difference in seconds for a match.

    Returns:
        Dict with keys ``offset``, ``points``, ``attrs``.
    """
    if current is None:
        raise ValueError("No GPX loaded")
    source = GPX(source_path)
    if offset is None:
        offset, _ = suggest_offset(current.gpx, source)
    points = attrs = 0
    if gpx := clone_next():
        points, attrs = fuse_segments(gpx, source, offset=offset, max_time=max_time)
    return {"offset": offset, "points": points, "attrs": attrs}


def suggest_offset_gpx(source_path: str) -> dict[str, float]:
    """Suggest the time offset between the current GPX and a source file.

    Args:
        source_path: Path to the source GPX file (in the Pyodide FS).

    Returns:
        Dict with keys ``offset``, ``residual``.
    """
    if current is None:
        raise ValueError("No GPX loaded")
    source = GPX(source_path)
    offset, residual = suggest_offset(current.gpx, source)
    return {"offset": offset, "residual": residual}
