"""CLI entry point for gphix."""

import argparse
import sys
from pathlib import Path
from typing import TextIO

from .gpx import GPX


def main(args: list[str] | None = None, out: TextIO = sys.stdout) -> None:
    """CLI entry point for gphix."""
    parser = argparse.ArgumentParser(
        prog="gphix",
        description="A toolbox to edit and fix issues with GPX files.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- stats ---
    stats_parser = subparsers.add_parser(
        "stats", help="Display statistics for a GPX file"
    )
    stats_parser.add_argument("gpx_file", type=Path, help="Path to the GPX file")

    parsed = parser.parse_args(args)

    if parsed.command == "stats":
        _cmd_stats(parsed.gpx_file, out)
    else:
        parser.print_help(out)


def _cmd_stats(gpx_file: Path, out: TextIO) -> None:
    """Handle the ``stats`` subcommand."""

    gpx = GPX(gpx_file)
    stats = gpx.stats()

    print(f"File: {gpx_file.name}", file=out)
    print(f"Points: {stats.points}", file=out)
    print(f"Distance: {_format_distance(stats.distance_m)}", file=out)
    if stats.duration_s is not None:
        print(f"Duration: {_format_duration(stats.duration_s)}", file=out)
    else:
        print("Duration: N/A", file=out)
    if stats.start_time and stats.end_time:
        print(f"Start: {stats.start_time.isoformat()}", file=out)
        print(f"End:   {stats.end_time.isoformat()}", file=out)
    else:
        print("Time: N/A", file=out)
    if stats.min_elev is not None and stats.max_elev is not None:
        print(f"Elevation: {stats.min_elev:.0f} – {stats.max_elev:.0f} m", file=out)
    else:
        print("Elevation: N/A", file=out)
    print(
        f"BBox: ({stats.min_lat:.6f}, {stats.min_lon:.6f}) – "
        f"({stats.max_lat:.6f}, {stats.max_lon:.6f})",
        file=out,
    )


def _format_distance(meters: float) -> str:
    if meters >= 1000:
        km = meters / 1000
        return f"{km:.2f} km" if km >= 1 else f"{meters:.0f} m"
    return f"{meters:.0f} m"


def _format_duration(seconds: float) -> str:
    """Return a human-readable duration string."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)
