"""CLI entry point for gphix."""

import argparse
import sys
from io import BytesIO
from pathlib import Path
from typing import TextIO

from .gpx import GPX, GPXStats


def _output_result(
    data: bytes, summary_lines: list[str], output: Path, out: TextIO
) -> None:
    """Write GPX data and optional summary to the target output."""
    if output == Path("-"):
        print(data.decode(), end="", file=out)
    else:
        with open(output, "wb") as f:
            f.write(data)
        for line in summary_lines:
            print(line, file=out)


def _add_output_arg(parser: argparse.ArgumentParser) -> None:
    """Add the shared -o/--output argument to a parser."""
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default="-",
        help="Output GPX file path (use - for stdout)",
    )


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
    stats_parser.add_argument("gpx_file", type=Path, help="Path to the GPX file")

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
    trim_parser.add_argument(
        "input", type=Path, help="Input GPX file (use - for stdin)"
    )
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

    parsed = parser.parse_args(args)

    if parsed.command == "stats":
        _cmd_stats(parsed.gpx_file, out)
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
    else:
        parser.print_help(out)


def _cmd_stats(gpx_file: Path, out: TextIO) -> None:
    """Handle the ``stats`` subcommand."""
    gpx = GPX(gpx_file)
    stats = gpx.stats()

    print(f"File: {gpx_file.name}", file=out)
    for line in _format_stats(stats):
        print(line, file=out)


def _cmd_merge(input_files: list[Path], output: Path, out: TextIO) -> None:
    """Handle the ``merge`` subcommand."""
    merged = GPX.merge(input_files)  # type: ignore
    data = merged.to_string().encode()
    summary = []
    if output != Path("-"):
        stats = merged.stats()
        summary = [f"Merged {len(input_files)} file(s) → {output}"]
        summary.extend(_format_stats(stats, prefix="  "))
    _output_result(data, summary, output, out)


def _format_stats(stats: GPXStats, prefix: str = "") -> list[str]:
    """Format common stats into lines with the given *prefix*.

    Args:
        stats: The statistics to format.
        prefix: Leading whitespace for each line (e.g. ``"  "`` for summaries).
    """
    lines: list[str] = [
        f"{prefix}Points: {stats.points}",
        f"{prefix}Tracks: {stats.tracks}",
        f"{prefix}Distance: {_format_distance(stats.distance)}",
    ]
    if stats.duration is not None:
        lines.append(f"{prefix}Duration: {_format_duration(stats.duration)}")
    else:
        lines.append(f"{prefix}Duration: N/A")
    if stats.start_time and stats.end_time:
        lines.append(f"{prefix}Start: {stats.start_time.isoformat()}")
        lines.append(f"{prefix}End: {stats.end_time.isoformat()}")
    else:
        lines.append(f"{prefix}Time: N/A")
    if stats.min_elev is not None and stats.max_elev is not None:
        lines.append(
            f"{prefix}Elevation: {stats.min_elev:.0f} – {stats.max_elev:.0f} m"
        )
    else:
        lines.append(f"{prefix}Elevation: N/A")
    lines.append(
        f"{prefix}BBox: ({stats.min_lat:.6f}, {stats.min_lon:.6f}) – "
        f"({stats.max_lat:.6f}, {stats.max_lon:.6f})"
    )
    return lines


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
    if input_file == Path("-"):
        gpx = GPX(stdin or BytesIO(sys.stdin.buffer.read()))
    else:
        gpx = GPX(input_file)

    orig_stats = gpx.stats()
    if not by_time and not by_distance:
        start /= 100
        end /= 100
    trimmed = gpx.trim(start=start, end=end, by_time=by_time, by_distance=by_distance)
    new_stats = trimmed.stats()

    removed = orig_stats.points - new_stats.points
    dist_saved = orig_stats.distance - new_stats.distance
    summary: list[str] = [f"Trimmed {input_file} → {output}"]
    summary.extend(_format_stats(new_stats, prefix="  "))
    summary.append(f"  Removed: {removed} points ({_format_distance(dist_saved)})")
    _output_result(trimmed.to_string().encode(), summary, output, out)
