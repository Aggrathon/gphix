"""Helper functions for the Pyodide powered Web UI."""

from dataclasses import dataclass
from pathlib import Path

from gphix.gpx import GPX
from gphix.utils import format_distance, format_duration, format_int


@dataclass(slots=True)
class AppState:
    gpx: GPX
    files: list[str]
    stats: list[tuple[str, str]] | None = None
    meta: dict | None = None
    segments: list[list[dict]] | None = None


current: AppState | None = None
previous: list[AppState] = []


def reset():
    global current
    if current is not None:
        previous.append(current)
        current = None


def undo():
    global current
    if previous:
        current = previous.pop()
    elif current is not None:
        previous.append(current)
        current = None


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


def get_stats() -> list[tuple[str, str]]:
    if current is None:
        return []
    if current.stats is None:
        stats = current.gpx.stats()
        current.stats = [
            ("points", format_int(stats.points)),
            ("tracks", format_int(stats.tracks)),
            ("distance", format_distance(stats.distance)),
            ("duration", format_duration(stats.duration)),
        ]
        if stats.start_time:
            current.stats.append(
                ("Start", stats.start_time.strftime("%Y-%m-%d %H:%M:%S"))
            )
        if stats.end_time:
            current.stats.append(("End", stats.end_time.strftime("%Y-%m-%d %H:%M:%S")))
        if stats.min_elev is not None and stats.max_elev is not None:
            current.stats.append(
                ("Elevation", f"{stats.min_elev:.0f} - {stats.max_elev:.0f} m")
            )
    return current.stats


def get_metadata() -> dict:
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


def get_segments() -> list[list[dict]]:
    if current is None:
        return []
    if current.segments is None:
        current.segments = [
            [
                {
                    "lat": p.latitude,
                    "lon": p.longitude,
                    "ele": p.elevation,
                    "time": p.time.isoformat() if p.time else None,
                }
                for p in seg.points()
            ]
            for seg in current.gpx.segments(True)
        ]
    return current.segments


def get_files() -> list[str]:
    if current is None:
        return []
    else:
        return current.files
