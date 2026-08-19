"""CLI entry point for gphix."""

import argparse
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Literal, TextIO

from gphix.trim import trim
from gphix.utils import format_distance, format_duration

from .elevation import add_elevation_to_gpx
from .fix import ReferencePaths, fill_gaps, find_frozen, find_gaps, fix_frozen
from .gpx import GPX, GPXMetadata, GPXStats


def _parse_trim_value(s: str) -> tuple[float, Literal["i", "s", "m", "p"]]:
    """Parse a trim value with optional unit suffix.

    Returns `(value, unit)` where unit is one of `i` (points), `m` (metres), `s` (seconds), `p` (percent).
    """
    if not s:
        return 0, "i"
    if s[-1] in ["%", "p"]:
        return float(s[:-1]) / 100, "p"
    if s[-1] in ["m", "s", "i"]:
        return float(s[:-1]), s[-1]
    else:
        return int(s), "i"


def _add_output_arg(parser: argparse.ArgumentParser, default: bool = True):
    """Add the shared -o/--output argument to a parser."""
    help = f"Output GPX file path ({'defaults to ' if default else ''} - for stdout)"
    parser.add_argument(
        "-o", "--output", type=Path, default="-" if default else None, help=help
    )


def _add_input_arg(parser: argparse.ArgumentParser):
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
):
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
        type=_parse_trim_value,
        default=(0, "i"),
        help="Points to remove from the beginning. Suffixes: m=metres, s=seconds, %%=percent (default: 0)",
    )
    trim_parser.add_argument(
        "--end",
        type=_parse_trim_value,
        default=(0, "i"),
        help="Points to remove from the end. Suffixes: m=metres, s=seconds, %%=percent (default: 0)",
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

    # --- fix ---
    fix_parser = subparsers.add_parser(
        "fix",
        help="Fix GPS tracks by filling in gaps between segments and fixing frozen coordinates (lost signal)",
    )
    _add_input_arg(fix_parser)
    fix_parser.add_argument(
        "ref",
        type=Path,
        nargs="?",
        default=None,
        help="Reference GPX file (instead of a linear interpolation use this path for filling gaps)",
    )
    _add_output_arg(fix_parser, False)
    fix_parser.add_argument(
        "--list",
        action="store_true",
        help="List gaps and frozen section without modifying ",
    )
    fix_parser.add_argument(
        "--min-distance",
        type=float,
        default=100.0,
        help="Minimum distance in metres to detect (default: 100)",
    )
    fix_parser.add_argument(
        "--min-time",
        type=float,
        default=-1.0,
        help="Minimum duration in seconds to detect (default: -1)",
    )
    fix_parser.add_argument(
        "--min-frozen",
        type=int,
        default=3,
        help="Minimum number of frozen points to detect (default: 3)",
    )
    fix_parser.add_argument(
        "--select",
        "-s",
        type=str,
        action="append",
        default=None,
        help='Fix only specific items by --list index (e.g. "-s 2 -s 3,5-8,11" selects [2,3,5,6,7,8,11])',
    )
    fix_parser.add_argument(
        "--no-frozen",
        action="store_true",
        default=False,
        help="Disable frozen coordinate fix",
    )
    fix_parser.add_argument(
        "--no-gaps",
        action="store_true",
        default=False,
        help="Disable gap filling",
    )

    # --- elevation ---
    elev_parser = subparsers.add_parser(
        "elevation", help="Add elevation data from external sources to a GPX file"
    )
    _add_input_arg(elev_parser)
    _add_output_arg(elev_parser)
    elev_parser.add_argument(
        "elevation_sources",
        type=Path,
        nargs="+",
        help="Elevation sources (GPX files, DEM files, or archives)",
    )
    elev_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing elevation data",
    )
    elev_parser.add_argument(
        "--radius",
        type=float,
        default=50.0,
        help="Max perpendicular distance (m) to GPX track edge (default: 50)",
    )

    # --- clean ---
    clean_parser = subparsers.add_parser(
        "clean", help="Clean up GPX files (remove empty segments, outliers)"
    )
    _add_input_arg(clean_parser)
    _add_output_arg(clean_parser)
    clean_parser.add_argument(
        "--outliers",
        action="store_true",
        help="Remove singular points with odd jumps (based on --max-distance or --max-time)",
    )
    clean_parser.add_argument(
        "--max-distance",
        type=float,
        default=100.0,
        help="Outlier threshold in metres (default: 100)",
    )
    clean_parser.add_argument(
        "--max-time",
        type=float,
        default=float("inf"),
        help="Outlier threshold in seconds (default: inf)",
    )
    clean_parser.add_argument(
        "--min-size", type=int, default=1, help="Remove smaller segments (default: 1)"
    )
    clean_parser.add_argument(
        "--merge-tracks", action="store_true", help="Merge all tracks into one"
    )
    clean_parser.add_argument(
        "--bounds", action="store_true", help="Add bounds to metadata"
    )

    # --- tracks ---
    tracks_parser = subparsers.add_parser("tracks", help="View or edit track metadata")
    _add_input_arg(tracks_parser)
    _add_output_arg(tracks_parser, default=False)
    tracks_parser.add_argument(
        "-t", "--track", type=int, default=None, help="Edit only target track"
    )
    tracks_parser.add_argument("--name", default=None, help="Set name")
    tracks_parser.add_argument("--description", default=None, help="Set description")
    tracks_parser.add_argument("--type", default=None, help="Set type")

    # --- meta ---
    meta_parser = subparsers.add_parser(
        "meta", help="Edit metadata fields of a GPX file"
    )
    _add_input_arg(meta_parser)
    _add_output_arg(meta_parser)
    meta_parser.add_argument("--name", default=None)
    meta_parser.add_argument("--description", "--desc", default=None)
    meta_parser.add_argument("--author", default=None)
    meta_parser.add_argument("--email", default=None)
    meta_parser.add_argument("--copyright", default=None)
    meta_parser.add_argument("--keywords", default=None)

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
    elif parsed.command == "elevation":
        _cmd_elevation(
            parsed.input,
            parsed.elevation_sources,
            parsed.output,
            parsed.overwrite,
            parsed.radius,
            out,
            stdin,
        )
    elif parsed.command == "fix":
        _cmd_fix(
            parsed.input,
            parsed.ref,
            parsed.output,
            parsed.list,
            parsed.min_distance,
            parsed.min_time,
            parsed.select,
            parsed.no_frozen,
            parsed.no_gaps,
            parsed.min_frozen,
            out,
            stdin,
        )
    elif parsed.command == "clean":
        _cmd_clean(
            parsed.input,
            parsed.output,
            parsed.outliers,
            parsed.max_distance,
            parsed.max_time,
            parsed.min_size,
            parsed.merge_tracks,
            parsed.bounds,
            out,
            stdin,
        )
    elif parsed.command == "meta":
        _cmd_meta(
            parsed.input,
            parsed.output,
            parsed.name,
            parsed.description,
            parsed.author,
            parsed.email,
            parsed.copyright,
            parsed.keywords,
            out,
            stdin,
        )
    elif parsed.command == "tracks":
        _cmd_tracks(
            parsed.input,
            parsed.output,
            parsed.track,
            parsed.name,
            parsed.description,
            parsed.type,
            out,
            stdin,
        )
    else:
        parser.print_help(out)


def _cmd_stats(input_file: Path, out: TextIO, stdin: BytesIO | None = None):
    """Handle the ``stats`` subcommand."""
    gpx = _load_gpx(input_file, stdin)
    print(f"File: {input_file.name}", file=out)
    _print_stats(gpx, out, prefix="")


def _cmd_merge(input_files: list[Path], output: Path, out: TextIO):
    """Handle the ``merge`` subcommand."""
    merged = GPX.merge(input_files)  # type: ignore
    if output != Path("-"):
        merged.write(output)
        print(f"Merged {len(input_files)} file(s) → {output}", file=out)
        _print_stats(merged, out)
    else:
        out.write(merged.to_string())


def _print_stats(gpx: GPX, out: TextIO, prefix: str = "  ") -> GPXStats:
    """Print common stats lines to *out* with the given *prefix*."""
    metadata = gpx.metadata()
    if metadata is not None:
        if metadata.name:
            print(f"{prefix}Name: {metadata.name}", file=out)
        if metadata.description:
            print(f"{prefix}Description: {metadata.description}", file=out)
        if metadata.author or metadata.email:
            author = metadata.author or ""
            if metadata.email:
                author += f" <{metadata.email}>"
            print(f"{prefix}Author: {author}", file=out)
        if metadata.copyright:
            print(f"{prefix}Copyright: {metadata.copyright}", file=out)
        if metadata.keywords:
            print(f"{prefix}Keywords: {metadata.keywords}", file=out)
        if metadata.links:
            print(f"{prefix}Links:", file=out)
            for link, name, _ in metadata.links:
                print(f"{prefix}  {name}: {link}", file=out)
    stats = gpx.stats()
    print(f"{prefix}Points: {stats.points}", file=out)
    print(f"{prefix}Tracks: {stats.tracks}", file=out)
    tracks = gpx.tracks()
    if tracks and any(t.name for t in tracks):
        for track in gpx.tracks():
            print(f"  - {track.name or '(no name)'}", file=out)
    print(f"{prefix}Distance: {format_distance(stats.distance)}", file=out)
    print(f"{prefix}Duration: {format_duration(stats.duration)}", file=out)
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
    if metadata is not None and metadata.max_lat is not None:
        print(
            f"{prefix}Bounds: {metadata.min_lat},{metadata.min_lon} - {metadata.max_lat},{metadata.max_lon}",
            file=out,
        )
    return stats


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


def _cmd_elevation(
    input_file: Path,
    elevation_sources: list[Path],
    output: Path,
    overwrite: bool,
    radius: float,
    out: TextIO,
    stdin: BytesIO | None = None,
):
    """Handle the ``elevation`` subcommand."""
    gpx = _load_gpx(input_file, stdin)

    updates = add_elevation_to_gpx(
        gpx, elevation_sources, overwrite=overwrite, radius=radius
    )

    if output != Path("-"):
        gpx.write(output)
        print(f"Added elevation to {input_file} → {output}", file=out)
        _print_stats(gpx, out)
        print(f"Updated: {updates} point(s)", file=out)
    else:
        out.write(gpx.to_string())


def _cmd_insert(
    input_file: Path,
    output: Path,
    tokens: list[str],
    out: TextIO,
    stdin: BytesIO | None = None,
):
    """Handle the ``insert`` subcommand."""
    gpx = _load_gpx(input_file, stdin)
    parsed = _parse_points(tokens)
    gpx.add_track(*parsed)
    if output != Path("-"):
        gpx.write(output)
        print(f"Inserted {len(parsed)} point(s) into {input_file} → {output}", file=out)
        _print_stats(gpx, out)
    else:
        out.write(gpx.to_string())


def _parse_select(raw: list[str] | None) -> list[int] | None:
    """Parse --select argument into a flat list of indices."""
    if raw is None:
        return None
    indices: list[int] = []
    for group in raw:
        for x in group.split(","):
            if "-" in x:
                a, b = x.split("-")
                indices.extend(range(int(a), int(b) + 1))
            else:
                indices.append(int(x))
    return indices


def _cmd_fix(
    input_file: Path,
    ref_file: Path | None,
    output: Path,
    list_gaps: bool,
    min_distance: float,
    min_time: float,
    select: list[str] | None,
    no_frozen: bool,
    no_gaps: bool,
    min_frozen: int,
    out: TextIO,
    stdin: BytesIO | None = None,
):
    """Handle the ``fill`` subcommand."""
    if no_frozen and no_gaps:
        return print(
            "Cannot disable both frozen fixing and gap filling at the same time",
            file=out,
        )
    gpx = _load_gpx(input_file, stdin)

    if list_gaps:

        def print_gap(i: int, gap):
            print(
                f"{i}  {gap.start.lat:.5f},{gap.start.lon:.5f} →",
                f"{gap.end.lat:.5f},{gap.end.lon:.5f} ",
                f"dist={format_distance(gap.distance)} ",
                f"duration={format_duration(gap.duration) if gap.duration is not None else 'N/A'} ",
                f"length={len(gap.points) - 2}" if gap.points else "",
                file=out,
            )

        if no_gaps:
            gaps = []
        else:
            gaps = find_gaps(gpx, min_distance, min_time)
            print("Gaps:" if gaps else "No gaps", file=out)
            for i, gap in enumerate(gaps):
                print_gap(i, gap)
        if not no_frozen:
            frozen = find_frozen(gpx, min_distance, min_time, min_frozen)
            print("Frozen sections:" if frozen else "No frozen sections", file=out)
            for i, sec in enumerate(frozen):
                print_gap(i + len(gaps), sec)
        return

    ref = ReferencePaths(_load_gpx(ref_file, stdin) if ref_file else None)
    selected = _parse_select(select)
    gaps = sections = None
    if selected is not None:
        if no_gaps:
            sections = selected
        elif no_frozen:
            gaps = selected
        else:
            ngaps = len(find_gaps(gpx, min_distance, min_time))
            gaps = [s for s in selected if s < ngaps]
            sections = [s - ngaps for s in selected if s >= ngaps]
    ngap = nfrozen = 0
    if not no_gaps:
        ngap = fill_gaps(gpx, ref, min_distance, min_time, gaps)
    if not no_frozen:
        nfrozen = fix_frozen(gpx, ref, min_distance, min_time, min_frozen, sections)

    if output != Path("-"):
        gpx.write(output)
        upd = []
        if not no_gaps:
            upd.append(f"{ngap} gap(s)")
        if not no_frozen:
            upd.append(f"{nfrozen} frozen point(s)")
        print(f"Fixed {' and '.join(upd)} from {ref_file} → {output}", file=out)
        _print_stats(gpx, out)
    else:
        out.write(gpx.to_string())


def _cmd_trim(
    input_file: Path,
    output: Path,
    start: tuple[float, Literal["i", "s", "m", "p"]],
    end: tuple[float, Literal["i", "s", "m", "p"]],
    out: TextIO,
    stdin: BytesIO | None = None,
):
    """Handle the ``trim`` subcommand."""
    gpx = _load_gpx(input_file, stdin)
    if output != Path("-"):
        orig_stats = gpx.stats()
        trim(gpx, *start, *end)
        gpx.write(output)
        print(f"Trimmed {input_file} → {output}", file=out)
        new_stats = _print_stats(gpx, out)
        removed = orig_stats.points - new_stats.points
        dist_saved = orig_stats.distance - new_stats.distance
        print(f"Removed: {removed} points ({format_distance(dist_saved)})", file=out)
    else:
        trim(gpx, *start, *end)
        out.write(gpx.to_string())


def _cmd_clean(
    input_file: Path,
    output: Path,
    outliers: bool,
    max_distance: float,
    max_time: float,
    min_size: int,
    merge_tracks: bool,
    add_bounds: bool,
    out: TextIO,
    stdin: BytesIO | None = None,
):
    """Handle the ``clean`` subcommand."""
    gpx = _load_gpx(input_file, stdin)
    gpx.clean(
        outliers=outliers,
        max_distance=max_distance,
        max_time=max_time,
        min_size=min_size,
        merge_tracks=merge_tracks,
        add_bounds=add_bounds,
    )
    if output != Path("-"):
        gpx.write(output)
        print(f"Cleaned {input_file} → {output}", file=out)
        _print_stats(gpx, out)
    else:
        out.write(gpx.to_string())


def _cmd_meta(
    input_file: Path,
    output: Path,
    name: str | None,
    description: str | None,
    author: str | None,
    email: str | None,
    copyright: str | None,
    keywords: str | None,
    out: TextIO,
    stdin: BytesIO | None = None,
):
    """Handle the ``meta`` subcommand."""
    gpx = _load_gpx(input_file, stdin)
    meta = gpx.metadata()
    if meta is None:
        meta = GPXMetadata()
    if name is not None:
        meta.name = name
    if description is not None:
        meta.description = description
    if author is not None:
        meta.author = author
    if email is not None:
        meta.email = email
    if copyright is not None:
        meta.copyright = copyright
    if keywords is not None:
        meta.keywords = keywords
    gpx.set_metadata(meta)
    if output != Path("-"):
        gpx.write(output)
        print(f"Updated metadata for {input_file} → {output}", file=out)
        _print_stats(gpx, out)
    else:
        out.write(gpx.to_string())


def _cmd_tracks(
    input_file: Path,
    output: Path | None,
    track_index: int | None,
    name: str | None,
    description: str | None,
    track_type: str | None,
    out: TextIO,
    stdin: BytesIO | None = None,
):
    """Handle the ``tracks`` subcommand."""
    gpx = _load_gpx(input_file, stdin)
    tracks = gpx.tracks()
    for t in tracks if track_index is None else (tracks[track_index],):
        if name is not None:
            t.name = name
        if description is not None:
            t.description = description
        if track_type is not None:
            t.track_type = track_type
    if output == Path("-"):
        return out.write(gpx.to_string())
    if output:
        gpx.write(output)
        print(f"Updated track metadata for {input_file} → {output}", file=out)
    for i, track in enumerate(gpx.tracks()):
        print(f"Track {i}:", file=out)
        print(f"    Name: {track.name or ''}", file=out)
        print(f"    Desc: {track.description or ''}", file=out)
        print(f"    Type: {track.track_type or ''}", file=out)
