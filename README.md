# <img alt="logo" src="favicon.svg" height="30"> GPhiX 

A toolbox for editing and fixing GPX files. Use it in your [browser](https://aggrathon.github.io/gphix/), or from the command line, or as a Python library.

## Functionality

All interfaces support the same core operations:

- **Merge** — Combine multiple GPX files into one
- **Metadata** — Edit GPX-level and track-level metadata
- **Trim** — Remove points from the start and end, by count, distance, time, or percentage
- **Insert** — Add new points as a new track
- **Elevation** — Add (missing) elevation data from DEM files or GPX references
- **Fix** — Fill gaps between segments and repair frozen coordinates using reference tracks or linear interpolation
- **Clean** — Remove empty segments, outlier points with odd jumps, merge tracks, and add bounds

## Web App

The easiest way to get started. Open the [web app](https://aggrathon.github.io/gphix/) in your browser — no installation required. All processing runs locally; nothing leaves your machine. The web app also shows the GPS tracks on a map and in plots.

## CLI

To install. run [`uv`](https://github.com/astral-sh/uv)`tool install git+https://github.com/Aggrathon/gphix`.
Then use `gphix --help` and `gphix <subcommand> --help` for usage details. Supports stdin/stdout via `-`.

Alternatively, to run without installing use `uvx git+https://github.com/Aggrathon/gphix --help`.

## Library

To install the library, clone the repo and run `uv sync`. This also provides access to the `gphix` CLI.
Or use `uv add git+https://github.com/Aggrathon/gphix` to add it as an dependency of existing projects.

```py
from gphix import GPX
```
The package has minimal dependencies — `numpy`, `rasterio`, and `scipy` are only loaded when needed (elevation lookups and spatial indexing).

## Development

After cloning set up the environment with `uv sync`. Please use auto formatting (`uv run ruff check` or black). Run tests with `uv run pytest` (coverage enforced at 95%). Capture a profile with `uv run python -m cProfile -o prof.out -m gphix.cli stats input.gpx` and view it with `uv run snakeviz prof.out`.
