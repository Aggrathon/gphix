"""CLI entry point for gphix."""

import argparse
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TextIO

from .gpx import GPX, GPXStats


def _add_output_arg(parser: argparse.ArgumentParser) -> None:
    """Add the shared -o/--output argument to a parser."""
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default="-",
        help="Output GPX file path (use - for stdout)",
    )


def _add_input_arg(parser: argparse.ArgumentParser) -> None:
    """Add the shared input file argument to a parser."""
    parser.add_argument("input", type=Path, help="Input GPX file (use - for stdin)")


def _load_gpx(source: Path, stdin: BytesIO | None = None) -> GPX:
    """Load a GPX from a file path or stdin (when *source* is ``Path("-")``)."""
    if source == Path("-"):
        raw = stdin or BytesIO(sys.stdin.buffer.read())
        return GPX(raw)
    return GPX(source)


def main(
    args: list[str] | None = None,
    out: TextIO = sys.stdout,
    stdin: BytesIO | None = None,
) -> None:
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
    _add_input_arg(stats_parser)

    # --- merge ---
    merge_parser = subparsers.add_parser(
        "merge", help="Merge multiple GPX files into one"
    )
    merge_parser.add_argument(
        "input_files", type=Path, nargs="+", help="Input GPX files to merge"
    )
    _add_output_arg(merge_parser)

    # --- trim ---
    trim_parser = subparsers.add_parser(
        "trim", help="Trim points from the start and end of tracks"
    )
    _add_input_arg(trim_parser)
    _add_output_arg(trim_parser)
    trim_parser.add_argument(
        "--start",
        type=float,
        default=0.0,
        help="Percentage (0–100) to remove from the beginning (default: 0)",
    )
    trim_parser.add_argument(
        "--end",
        type=float,
        default=0.0,
        help="Percentage (0–100) to remove from the end (default: 0)",
    )
    trim_excl = trim_parser.add_mutually_exclusive_group()
    trim_excl.add_argument(
        "--time",
        action="store_true",
        help="Treat --start/--end as seconds (default: percent)",
    )
    trim_excl.add_argument(
        "--distance",
        action="store_true",
        help="Treat --start/--end as metres (default: percent)",
    )

    # --- insert ---
    insert_parser = subparsers.add_parser(
        "insert",
        help="Insert new points as a new track in a GPX file",
    )
    _add_input_arg(insert_parser)
    _add_output_arg(insert_parser)
    insert_parser.add_argument(
        "points",
        nargs="+",
        help="Points as comma-separated values: 'lat,lon' or 'lat,lon,ele' or 'lat,lon,ele,time'",
    )

    parsed = parser.parse_args(args)

    if parsed.command == "stats":
        _cmd_stats(parsed.input, out, stdin)
    elif parsed.command == "merge":
        _cmd_merge(parsed.input_files, parsed.output, out)
    elif parsed.command == "trim":
        _cmd_trim(
            parsed.input,
            parsed.output,
            parsed.start,
            parsed.end,
            parsed.time,
            parsed.distance,
            out,
            stdin,
        )
    elif parsed.command == "insert":
        _cmd_insert(
            parsed.input,
            parsed.output,
            parsed.points,
            out,
            stdin,
        )
    else:
        parser.print_help(out)


def _cmd_stats(input_file: Path, out: TextIO, stdin: BytesIO | None = None) -> None:
    """Handle the ``stats`` subcommand."""
    gpx = _load_gpx(input_file, stdin)
    stats = gpx.stats()

    print(f"File: {input_file.name}", file=out)
    _print_stats(stats, out, prefix="")


def _cmd_merge(input_files: list[Path], output: Path, out: TextIO) -> None:
    """Handle the ``merge`` subcommand."""
    merged = GPX.merge(input_files)  # type: ignore
    if output != Path("-"):
        merged.write(output)
        print(f"Merged {len(input_files)} file(s) → {output}", file=out)
        _print_stats(merged.stats(), out)
    else:
        out.write(merged.to_string())


def _print_stats(stats: GPXStats, out: TextIO, prefix: str = "  ") -> None:
    """Print common stats lines to *out* with the given *prefix*."""
    print(f"{prefix}Points: {stats.points}", file=out)
    print(f"{prefix}Tracks: {stats.tracks}", file=out)
    print(f"{prefix}Distance: {_format_distance(stats.distance)}", file=out)
    print(f"{prefix}Duration: {_format_duration(stats.duration)}", file=out)
    if stats.start_time and stats.end_time:
        print(f"{prefix}Start: {stats.start_time.isoformat()}", file=out)
        print(f"{prefix}End: {stats.end_time.isoformat()}", file=out)
    else:
        print(f"{prefix}Time: N/A", file=out)
    if stats.min_elev is not None and stats.max_elev is not None:
        print(
            f"{prefix}Elevation: {stats.min_elev:.0f} – {stats.max_elev:.0f} m",
            file=out,
        )
    else:
        print(f"{prefix}Elevation: N/A", file=out)
    print(
        f"{prefix}BBox: ({stats.min_lat:.6f}, {stats.min_lon:.6f}) – "
        f"({stats.max_lat:.6f}, {stats.max_lon:.6f})",
        file=out,
    )


def _format_distance(meters: float) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.2f} km"
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


def _parse_points(
    point_strs: list[str],
) -> list[tuple[float, float, float | None, datetime | None]]:
    """Parse comma-separated point strings into (lat, lon, ele?, time?) tuples.

    Each string can have 2–4 fields:
        lat,lon
        lat,lon,ele
        lat,lon,ele,time
        lat,lon,time
    """
    points: list[tuple[float, float, float | None, datetime | None]] = []
    for s in point_strs:
        parts = s.split(",")
        if len(parts) < 2:
            raise ValueError(
                f"Invalid point format: '{s}'. Expected 'lat,lon[,ele[,time]]'"
            )
        lat = float(parts[0])
        lon = float(parts[1])
        ele = None
        time: datetime | None = None
        if len(parts) >= 3:
            try:
                ele = float(parts[2])
            except ValueError:
                ele = None
                time = datetime.fromisoformat(parts[2])
        if len(parts) >= 4 and time is None:
            time = datetime.fromisoformat(parts[3])
        points.append((lat, lon, ele, time))
    return points


def _cmd_insert(
    input_file: Path,
    output: Path,
    tokens: list[str],
    out: TextIO,
    stdin: BytesIO | None = None,
) -> None:
    """Handle the ``insert`` subcommand."""
    gpx = _load_gpx(input_file, stdin)

    parsed = _parse_points(tokens)
    track = gpx.add_track()
    for lat, lon, ele, time in parsed:
        pt = track.add_point(lat, lon)
        if ele is not None:
            pt.elevation = ele
        if time is not None:
            pt.time = time

    if output != Path("-"):
        gpx.write(output)
        print(f"Inserted {len(parsed)} point(s) into {input_file} → {output}", file=out)
        _print_stats(gpx.stats(), out)
    else:
        out.write(gpx.to_string())


def _cmd_trim(
    input_file: Path,
    output: Path,
    start: float,
    end: float,
    by_time: bool,
    by_distance: bool,
    out: TextIO,
    stdin: BytesIO | None = None,
) -> None:
    """Handle the ``trim`` subcommand."""
    gpx = _load_gpx(input_file, stdin)

    if not by_time and not by_distance:
        start /= 100
        end /= 100
    trimmed = gpx.trim(start=start, end=end, by_time=by_time, by_distance=by_distance)

    if output != Path("-"):
        orig_stats = gpx.stats()
        new_stats = trimmed.stats()
        removed = orig_stats.points - new_stats.points
        dist_saved = orig_stats.distance - new_stats.distance
        trimmed.write(output)
        print(f"Trimmed {input_file} → {output}", file=out)
        _print_stats(new_stats, out)
        print(f"Removed: {removed} points ({_format_distance(dist_saved)})", file=out)
    else:
        out.write(trimmed.to_string())
