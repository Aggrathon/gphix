from datetime import UTC, datetime
from os import PathLike


def create_gpx_file(
    gpx_path: PathLike,
    coords: list[tuple[float, float]] | None = None,
    elevation: bool | float | list[float] = False,
    time: bool | datetime | list[datetime] = False,
):
    """Create a minimal GPX track file for testing.

    Args:
        gpx_path: Output file path.
        coords: (lat, lon) pairs. Defaults to Paris, London, New York.
        elevation: `False` = no elevation, `True` = 100.0 m for all points,
            `float` = single value for all points, `list[float]` = one per point.
        time: `False` = no time, `True` = auto-generated sequential times,
            `datetime` = same time for all points, `list[datetime]` = one per point.
    """
    if coords is None:
        coords = [(48.8584, 2.2945), (51.5074, -0.1278), (40.7128, -74.006)]

    if elevation is False:
        elev = []
    elif elevation is True:
        elev = [100.0] * len(coords)
    elif isinstance(elevation, (float, int)):
        elev = [float(elevation)] * len(coords)
    else:
        elev = elevation

    if time is False:
        tm = []
    elif time is True:
        tm = [datetime(2024, 1, 1, 12, i, tzinfo=UTC) for i in range(len(coords))]
    elif isinstance(time, datetime):
        tm = [time] * len(coords)
    else:
        tm = time

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="GPeleX" xmlns="http://www.topografix.com/GPX/1/1">',
        "  <trk>",
        "    <trkseg>",
    ]
    for i, (lat, lon) in enumerate(coords):
        eles = f"<ele>{elev[i]}</ele>" if i < len(elev) else ""
        tms = f"<time>{tm[i].isoformat()}</time>" if i < len(tm) else ""
        lines.append(f'      <trkpt lat="{lat}" lon="{lon}">{eles}{tms}</trkpt>')
    lines.extend(["    </trkseg>", "  </trk>", "</gpx>"])

    with open(gpx_path, "w") as f:
        f.write("\n".join(lines))
