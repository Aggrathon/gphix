
def create_gpx_file(gpx_path: str, with_elevation: bool = False) -> None:
    """Create a test GPX file with or without elevation data."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="GPeleX" xmlns="http://www.topografix.com/GPX/1/1">',
        "  <trk>",
        "    <trkseg>",
    ]
    ele = "<ele>100.0</ele>" if with_elevation else ""
    for lat, lon in [(48.8584, 2.2945), (51.5074, -0.1278), (40.7128, -74.006)]:
        lines.append(f'      <trkpt lat="{lat}" lon="{lon}">{ele}</trkpt>')
    lines.extend(["    </trkseg>", "  </trk>", "</gpx>"])

    with open(gpx_path, "w") as f:
        f.write("\n".join(lines))
