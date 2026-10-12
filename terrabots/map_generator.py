"""
Terrain generation shared by survival (terrabots-run) and battle (terrabots-battle).

Every generator takes an explicit `rng` (a random.Random, or the `random` module
itself) so callers control reproducibility. Generators write elevations through
WorldGrid.set(), which keeps WorldGrid.elevation_map in sync.
"""

from __future__ import annotations

import math
import random
from typing import Protocol

from terrabots.world_terrain import Cell, TerrainType, WorldGrid


class Rng(Protocol):
    def random(self) -> float: ...
    def uniform(self, a: float, b: float) -> float: ...


def procedural(width: int, height: int, rng: Rng = random) -> WorldGrid:
    """Hills, lakes, rock peaks and stair clusters from summed sine waves.

    Elevation bands: < 0.4 water, > 5.0 rock, 2.5-3.5 occasionally stairs.
    """
    world = WorldGrid(width, height)

    freq1, freq2 = 0.09, 0.17
    a1, a2 = 3.5, 1.5
    # Random phase offsets give a different map per seed.
    ox1, oy1 = rng.uniform(0, 100), rng.uniform(0, 100)
    ox2, oy2 = rng.uniform(0, 100), rng.uniform(0, 100)

    for x in range(width):
        for y in range(height):
            h = (
                a1 * math.sin((x + ox1) * freq1) * math.cos((y + oy1) * freq1)
                + a2 * math.sin((x + ox2) * freq2 + 1.3) * math.sin((y + oy2) * freq2)
            )
            h = max(0.0, h + 1.0)
            elev = round(h, 3)

            if h < 0.4:
                cell = Cell(TerrainType.WATER, elev, water_depth=round(0.4 - h + 0.2, 2))
            elif h > 5.0:
                cell = Cell(TerrainType.ROCK, elev)
            elif 2.5 < h < 3.5 and rng.random() < 0.12:
                cell = Cell(TerrainType.STAIRS, elev)
            else:
                cell = Cell(TerrainType.PLAIN, elev)
            world.set(x, y, cell)

    return world


def flat(width: int, height: int) -> WorldGrid:
    """All PLAIN at elevation 0: the classic Robocode arena."""
    return WorldGrid(width, height)
