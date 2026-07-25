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

    # --- merge ---
    merge_parser = subparsers.add_parser(
        "merge", help="Merge multiple GPX files into one"
    )
    merge_parser.add_argument(
        "input_files", type=Path, nargs="+", help="Input GPX files to merge"
    )
    merge_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default="-",
        help="Output GPX file path (use - for stdout)",
    )

    parsed = parser.parse_args(args)

    if parsed.command == "stats":
        _cmd_stats(parsed.gpx_file, out)
    elif parsed.command == "merge":
        _cmd_merge(parsed.input_files, parsed.output, out)
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


def _cmd_merge(input_files: list[Path], output: Path, out: TextIO) -> None:
    """Handle the ``merge`` subcommand."""
    merged = GPX.merge(input_files)

    if output == Path("-"):
        # Write raw XML to stdout, nothing else
        print(merged.to_string(), end="", file=out)
    else:
        merged.write(output)

        stats = merged.stats()
        track_count = len(merged.root.findall("gpx:trk", merged.namespaces))
        waypoint_count = len(merged.root.findall("gpx:wpt", merged.namespaces))

        print(f"Merged {len(input_files)} file(s) → {output}", file=out)
        print(f"  Points:  {stats.points}", file=out)
        print(f"  Tracks:  {track_count}", file=out)
        print(f"  Waypts:  {waypoint_count}", file=out)
        print(f"  Distance: {_format_distance(stats.distance_m)}", file=out)


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
