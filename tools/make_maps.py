"""
Regenerate the built-in maps in terrabots/map_data/ (python tools/make_maps.py).

Each map is built from simple shapes so it can be reproduced and tweaked here;
every map is checked with terrabots.maps.check() for room and reachability.
Slopes stay at most 1 height unit per cell where tanks should drive (climb
limit 2); walls meant to block are steeper or rock.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrabots import map_generator, maps  # noqa: E402
from terrabots.world_terrain import Cell, TerrainType, WorldGrid  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "terrabots" / "map_data"


def build(elev: np.ndarray, kinds: np.ndarray) -> WorldGrid:
    """elev, kinds indexed [x, y]; kinds are letters P/R/W/S."""
    w, h = elev.shape
    world = WorldGrid(w, h)
    for x in range(w):
        for y in range(h):
            t = maps.CODES[kinds[x, y]]
            world.set(x, y, Cell(t, round(float(elev[x, y]), 2),
                                 maps.DEFAULT_WATER_DEPTH if t is TerrainType.WATER else 0.0))
    return world


def grid(w, h):
    xs, ys = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5, indexing="ij")
    return xs, ys


def arena():
    w = h = 48
    elev = np.zeros((w, h))
    kinds = np.full((w, h), "P")
    for cx, cy in ((12, 12), (36, 12), (12, 36), (36, 36), (24, 18), (24, 30)):
        elev[cx - 1:cx + 1, cy - 1:cy + 1] = 4.0
        kinds[cx - 1:cx + 1, cy - 1:cy + 1] = "R"
    return build(elev, kinds), "Arena", "Flat classic arena with six rock pillars to hide behind."


def twin_hills():
    w = h = 48
    xs, ys = grid(w, h)
    elev = 4.5 * (np.exp(-((xs - 14) ** 2 + (ys - 24) ** 2) / (2 * 6.5 ** 2))
                  + np.exp(-((xs - 34) ** 2 + (ys - 24) ** 2) / (2 * 6.5 ** 2)))
    kinds = np.full((w, h), "P")
    kinds[(elev > 2.4) & (elev < 3.0)] = "S"
    return build(elev, kinds), "Twin Hills", "Two round hills: high ground to see and shoot from, a valley between them to hide in."


def ridge():
    w = h = 48
    xs, ys = grid(w, h)
    elev = np.zeros((w, h))
    kinds = np.full((w, h), "P")
    band = (xs > 22) & (xs < 26)
    passes = (np.abs(ys - 8) < 2.5) | (np.abs(ys - 24) < 2.5) | (np.abs(ys - 40) < 2.5)
    wall = band & ~passes
    elev[wall] = 6.0
    kinds[wall] = "R"
    # gentle foothills either side
    elev += np.where(wall, 0, 1.2 * np.exp(-((xs - 24) ** 2) / 40) * ~passes)
    return build(elev, kinds), "Ridge", "A rock ridge splits the map in two; three passes connect the halves."


def lakes():
    w = h = 48
    xs, ys = grid(w, h)
    elev = np.full((w, h), 0.5)
    kinds = np.full((w, h), "P")
    for cx, cy, r in ((12, 12, 6), (36, 36, 6), (12, 36, 5), (36, 12, 5)):
        lake = (xs - cx) ** 2 + (ys - cy) ** 2 < r * r
        elev[lake] = 0.0
        kinds[lake] = "W"
    elev += 0.8 * np.exp(-((xs - 24) ** 2 + (ys - 24) ** 2) / 30) * (kinds == "P")
    return build(elev, kinds), "Lakes", "Four lakes; the fights happen on the land bridges between them."


def fortress():
    w = h = 48
    xs, ys = grid(w, h)
    elev = np.zeros((w, h))
    kinds = np.full((w, h), "P")
    plateau = (np.abs(xs - 24) < 8) & (np.abs(ys - 24) < 8)
    elev[plateau] = 3.0
    # ramps (one height unit per cell) in the middle of each side
    for d in range(1, 4):
        lvl = 3.0 - d * 0.75
        for sx, sy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            if sx == 0:
                ry = 24 + sy * (8 + d) - (1 if sy > 0 else 0)
                elev[21:27, ry] = lvl
                kinds[21:27, ry] = "S"
            else:
                rx = 24 + sx * (8 + d) - (1 if sx > 0 else 0)
                elev[rx, 21:27] = lvl
                kinds[rx, 21:27] = "S"
    for cx, cy in ((20, 20), (28, 20), (20, 28), (28, 28)):
        elev[cx - 1:cx + 1, cy - 1:cy + 1] = 6.0
        kinds[cx - 1:cx + 1, cy - 1:cy + 1] = "R"
    return build(elev, kinds), "Fortress", "A walled plateau in the middle, reachable over four ramps; whoever holds it sees everything."


def canyon():
    w, h = 64, 40
    xs, ys = grid(w, h)
    elev = np.where((ys < 13) | (ys > 27), 4.0, 0.0)
    kinds = np.full((w, h), "P")
    # ramps: 1 unit per cell from the canyon floor up to the plateaus
    for rx in (10, 32, 54):
        for i in range(4):
            elev[rx - 2:rx + 2, 12 - i] = 1.0 * (i + 1)
            elev[rx - 2:rx + 2, 27 + i] = 1.0 * (i + 1)
            kinds[rx - 2:rx + 2, 12 - i] = "S"
            kinds[rx - 2:rx + 2, 27 + i] = "S"
    rng = random.Random(4)
    for _ in range(10):
        cx, cy = rng.randrange(4, w - 4), rng.choice((rng.randrange(3, 9), rng.randrange(31, 37)))
        if all(abs(cx - rx) > 4 for rx in (10, 32, 54)):
            elev[cx - 1:cx + 1, cy - 1:cy + 1] = 7.0
            kinds[cx - 1:cx + 1, cy - 1:cy + 1] = "R"
    return build(elev, kinds), "Canyon", "A long canyon between two plateaus. Ramps lead up; the rim looks down on the canyon floor."


def badlands():
    world = map_generator.procedural(64, 64, rng=random.Random(7))
    return world, "Badlands", "Rough generated terrain: hills, lakes and rock peaks."


MAPS = [arena, twin_hills, ridge, lakes, fortress, canyon, badlands]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for make in MAPS:
        world, name, description = make()
        problems = maps.check(world)
        path = maps.save(maps.from_world(world, name, description, "Terrabots"), OUT)
        print(f"{path.name:18s} {world.width}x{world.height}  {'OK' if not problems else problems}")


if __name__ == "__main__":
    main()
