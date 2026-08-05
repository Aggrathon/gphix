"""Helper functions for the Pyodide powered Web UI."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from gphix.gpx import GPX
from gphix.utils import format_distance, format_duration, format_int

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(slots=True)
class Point:
    lat: float
    lon: float
    ele: float | None = None
    time: datetime | None = None

    def to_dict(self) -> dict[str, str | float | None]:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "ele": self.ele,
            "time": self.time.strftime(TIME_FORMAT) if self.time else None,
        }


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
            current.stats["Start"] = stats.start_time.strftime(TIME_FORMAT)
        if stats.end_time:
            current.stats["End"] = stats.end_time.strftime(TIME_FORMAT)
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


def get_point(seg_idx: int, pt_idx: int) -> dict[str, str | float | None]:
    if current is None or current.segments is None:
        return {}
    return current.segments[seg_idx][pt_idx].to_dict()


def get_point_idx(idx: int) -> tuple[int, int] | None:
    if current is None or not current.segments:
        return None
    if idx == -1:
        return len(current.segments) - 1, len(current.segments[-1]) - 1
    elif idx == 0:
        return 0, 0
    elif idx > 0:
        for i, seg in enumerate(current.segments):
            if idx < len(seg):
                return i, idx
            idx -= len(seg)
        return None
    else:
        raise NotImplementedError()


def get_files() -> list[str]:
    if current is None:
        return []
    else:
        return current.files
