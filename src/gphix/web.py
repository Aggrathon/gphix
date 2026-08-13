"""Helper functions for the Pyodide powered Web UI."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from gphix.elevation import add_elevation_to_gpx
from gphix.fill import fill_gaps, find_gaps
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
    gpx: GPX
    files: list[str]
    stats: dict[str, str] | None = None
    meta: dict[str, str | None] | None = None
    segments: list[list[Point]] | None = None


current: AppState | None = None
previous: list[AppState] = []


def reset():
    global current
    if current is not None:
        previous.append(current)
        current = None


def undo() -> bool:
    global current
    if previous:
        current = previous.pop()
    elif current is not None:
        previous.append(current)
        current = None
    return current is not None


def next(state: AppState):
    global current
    if current is None:
        previous.clear()
    else:
        previous.append(current)
    current = state


def clone_next() -> GPX | None:
    if current:
        gpx = deepcopy(current.gpx)
        next(AppState(gpx, current.files if current else []))
        return gpx


def load_gpx(root: str, paths: list[str]):
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
    if current is None:
        return {}
    if current.meta is None:
        meta = current.gpx.metadata()
        if not meta:
            current.meta = {}
        else:
            current.meta = {
                "name": meta.name,
                "description": meta.description,
                "author": meta.author,
                "email": meta.email,
                "copyright": meta.copyright,
                "keywords": meta.keywords,
                "time": meta.time.isoformat() if meta.time else None,
            }
    return current.meta


def get_segments() -> list[list[list[float]]]:
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
                pd = last.dist + distance((last.coord(), seg[0].coord()))
            for d, p in zip(cum_distance(p.coord() for p in seg), seg):
                p.dist = pd + d
            last = seg[-1]
    dist, time, elev = [], [], []
    for seg in current.segments:
        if dist:
            dist.append(dist[-1])
            time.append(None)
            elev.append(None)
        dist.extend(p.dist for p in seg)
        time.extend((p.time.timestamp() if p.time else None) for p in seg)
        elev.extend(p.ele for p in seg)
    return dist, time, elev


def get_point(
    seg_idx: int, pt_idx: int | None = None
) -> dict[str, str | float | None] | None:
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
    if current is None:
        return []
    else:
        return current.files


def set_metadata(
    name: str, description: str, author: str, email: str, copyright: str, keywords: str
):
    if gpx := clone_next():
        meta = gpx.metadata() or GPXMetadata()
        meta.name = name or None
        meta.description = description or None
        meta.author = author or None
        meta.email = email or None
        meta.copyright = copyright or None
        meta.keywords = keywords or None
        gpx.set_metadata(meta)


def trim_before(seg_idx: int, pt_idx: int):
    if gpx := clone_next():
        trim(gpx, start=(seg_idx, pt_idx))


def trim_after(seg_idx: int, pt_idx: int):
    if gpx := clone_next():
        trim(gpx, end=(seg_idx, pt_idx))


def apply_clean(
    min_size: int = 1,
    add_bounds: bool = False,
    outliers: bool = False,
    max_distance: float = 100.0,
    max_time: float = 70.0,
):
    if gpx := clone_next():
        gpx.clean(min_size, add_bounds, outliers, max_distance, max_time)


def apply_elevation(paths: list[str], radius: float = 50.0, overwrite: bool = False):
    if gpx := clone_next():
        add_elevation_to_gpx(gpx, paths, overwrite=overwrite, radius=radius)


def get_gaps(
    min_distance: float = 200.0, min_time: float = -1.0
) -> list[dict[str, str | float]]:
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
        }
        for g in find_gaps(current.gpx, min_distance, min_time)
    ]


def apply_fill_gaps(
    ref_path: str,
    min_distance: float = 200.0,
    min_time: float | None = None,
    selected_gaps: list[int] | None = None,
):
    if gpx := clone_next():
        ref = GPX(ref_path)
        return fill_gaps(gpx, ref, min_distance, min_time, selected_gaps)


def insert_points(rows: list[dict[str, str | float]]) -> None:
    """Add all rows as a single new track."""
    if gpx := clone_next():
        builder = gpx.add_track()
        for row in rows:
            lat = float(row["lat"])
            lon = float(row["lon"])
            ele = row.get("ele")
            time = row.get("time")
            time = datetime.fromisoformat(time) if time else None  # type:ignore
            ele = float(ele) if ele is not None and ele != "" else None
            builder.add_point(lat, lon, ele, time)


def save_gpx() -> str | None:
    """Return the current GPX as an XML string."""
    if current is None:
        return None
    return current.gpx.to_string()
