"""
Map files: hand-made or edited terrain, for battles and survival runs.

A map is a JSON file (format "terrabots-map/1"):

    {
      "format": "terrabots-map/1",
      "name": "Twin Hills", "description": "...", "author": "...",
      "width": 48, "height": 48,
      "elevation": [[0.0, 0.1, ...], ...],   # one row per y (south to north), x west to east
      "terrain":   ["PPPPRRWW...", ...],      # P plain, R rock, W water, S stairs; same layout
      "water_depth": [[...], ...]             # optional; water cells default to 0.6
    }

Where maps are found, by name: ./maps/<name>.json (your maps, the map builder
saves there) first, then the built-in maps shipped in terrabots/map_data/. A path to
a .json file works too.

check() reports problems that make a map unfair or unplayable, e.g. areas a tank
can't reach. The map builder shows its warnings before saving.
"""

from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any

from terrabots.world_terrain import Cell, TerrainType, WorldGrid

FORMAT = "terrabots-map/1"
BUILTIN_DIR = Path(__file__).with_name("map_data")
USER_DIR = Path("maps")
CODES = {"P": TerrainType.PLAIN, "R": TerrainType.ROCK, "W": TerrainType.WATER, "S": TerrainType.STAIRS}
LETTERS = {t: c for c, t in CODES.items()}
DEFAULT_WATER_DEPTH = 0.6
MAX_CLIMB = 2.0          # CreatureMoveProfile.max_climb_per_step default
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


class MapError(ValueError):
    """A map file that can't be loaded; the message says what's wrong."""


def slug(name: str) -> str:
    """'Twin Hills' -> 'twin-hills' (file names of maps)."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:41] or "map"


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def find(name: str) -> Path:
    """Path of a map given by name or path."""
    p = Path(name)
    if p.suffix == ".json" and p.exists():
        return p
    for d in (USER_DIR, BUILTIN_DIR):
        candidate = d / f"{name}.json"
        if candidate.exists():
            return candidate
    raise MapError(f"map {name!r} not found (looked in {USER_DIR}/ and the built-in maps)")


def read(name: str) -> dict[str, Any]:
    path = find(name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MapError(f"{path}: {exc}") from exc
    validate(data, str(path))
    return data


def load(name: str) -> WorldGrid:
    return to_world(read(name))


def validate(data: dict[str, Any], where: str = "map") -> None:
    if data.get("format") != FORMAT:
        raise MapError(f"{where}: not a {FORMAT} file")
    w, h = data.get("width"), data.get("height")
    if not (isinstance(w, int) and isinstance(h, int) and 16 <= w <= 256 and 16 <= h <= 256):
        raise MapError(f"{where}: width and height must be whole numbers from 16 to 256")
    elev, terr = data.get("elevation"), data.get("terrain")
    if not (isinstance(elev, list) and len(elev) == h and all(isinstance(r, list) and len(r) == w for r in elev)):
        raise MapError(f"{where}: elevation must be {h} rows of {w} numbers")
    if not (isinstance(terr, list) and len(terr) == h and all(isinstance(r, str) and len(r) == w for r in terr)):
        raise MapError(f"{where}: terrain must be {h} strings of {w} letters")
    bad = {c for row in terr for c in row} - set(CODES)
    if bad:
        raise MapError(f"{where}: unknown terrain letters {''.join(sorted(bad))} (use P, R, W, S)")
    for row in elev:
        for v in row:
            if not isinstance(v, (int, float)) or not (0 <= v <= 50):
                raise MapError(f"{where}: elevations must be numbers from 0 to 50")
    depth = data.get("water_depth")
    if depth is not None and not (isinstance(depth, list) and len(depth) == h
                                  and all(isinstance(r, list) and len(r) == w for r in depth)):
        raise MapError(f"{where}: water_depth must be {h} rows of {w} numbers")


def to_world(data: dict[str, Any]) -> WorldGrid:
    w, h = data["width"], data["height"]
    world = WorldGrid(w, h)
    depth = data.get("water_depth")
    for y in range(h):
        for x in range(w):
            t = CODES[data["terrain"][y][x]]
            d = depth[y][x] if depth is not None else (DEFAULT_WATER_DEPTH if t is TerrainType.WATER else 0.0)
            world.set(x, y, Cell(t, float(data["elevation"][y][x]), float(d) if t is TerrainType.WATER else 0.0))
    return world


def from_world(world: WorldGrid, name: str, description: str = "", author: str = "") -> dict[str, Any]:
    w, h = world.width, world.height
    cells = [[world.get(x, y) for x in range(w)] for y in range(h)]
    data: dict[str, Any] = {
        "format": FORMAT, "name": name, "description": description, "author": author,
        "width": w, "height": h,
        "elevation": [[round(c.elevation, 2) for c in row] for row in cells],
        "terrain": ["".join(LETTERS[c.terrain] for c in row) for row in cells],
    }
    if any(c.terrain is TerrainType.WATER and abs(c.water_depth - DEFAULT_WATER_DEPTH) > 1e-9
           for row in cells for c in row):
        data["water_depth"] = [[round(c.water_depth, 2) for c in row] for row in cells]
    return data


def save(data: dict[str, Any], directory: Path | None = None) -> Path:
    """Write a map to <directory>/<slug of its name>.json (default: ./maps/)."""
    validate(data)
    directory = USER_DIR if directory is None else directory
    directory.mkdir(parents=True, exist_ok=True)
    file = slug(data.get("name") or "map")
    path = directory / f"{file}.json"
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return path


def catalog() -> list[dict[str, Any]]:
    """All maps: your own (./maps/) first, then the built-in ones."""
    seen: set[str] = set()
    out = []
    for source, d in (("yours", USER_DIR), ("built-in", BUILTIN_DIR)):
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.json")):
            if path.stem in seen:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                validate(data, str(path))
            except (OSError, ValueError):
                continue
            seen.add(path.stem)
            out.append({"id": path.stem, "name": data.get("name", path.stem), "source": source,
                        "description": data.get("description", ""), "author": data.get("author", ""),
                        "width": data["width"], "height": data["height"]})
    return out


# ---------------------------------------------------------------------------
# Playability check
# ---------------------------------------------------------------------------

def check(world: WorldGrid, max_climb: float = MAX_CLIMB) -> list[str]:
    """Warnings about a map. A tank is ~3 cells wide, so only cells whose 3x3
    neighbourhood is enterable count as room for a tank; those should form one
    connected area, steps between them no steeper than the climb limit."""
    w, h = world.width, world.height

    def enterable(x: int, y: int) -> bool:
        c = world.get(x, y)
        return c.terrain is not TerrainType.ROCK and not (c.terrain is TerrainType.WATER and c.water_depth > 0)

    room = {(x, y) for x in range(1, w - 1) for y in range(1, h - 1)
            if all(enterable(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))}
    warnings = []
    if len(room) < 0.25 * w * h:
        warnings.append(f"only {len(room) * 100 // (w * h)} % of the map has room for a tank")
    if not room:
        return warnings + ["no room for a tank anywhere"]
    best: set = set()
    left = set(room)
    while left:
        start = left.pop()
        comp, todo = {start}, deque([start])
        while todo:
            x, y = todo.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n in left and abs(world.elevation_map[n] - world.elevation_map[x, y]) <= max_climb:
                    left.discard(n)
                    comp.add(n)
                    todo.append(n)
        if len(comp) > len(best):
            best = comp
    if len(best) < 0.85 * len(room):
        warnings.append(f"{100 - len(best) * 100 // len(room)} % of the drivable area can't be reached "
                        f"from the rest (cut off by rock, water or steps steeper than {max_climb:g})")
    return warnings
