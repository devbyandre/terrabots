"""
2.5D world terrain model: elevation- and water-depth-aware visibility and movement.

Design notes (assumptions made explicit, per request):
- Grid is a 2D plane; "height" is a scalar attribute per cell, not a true 3D coordinate.
- Elevation units and energy-cost units are both arbitrary floats; calibrate constants
  against actual gameplay balance once the rest of the sim exists. Values below are
  placeholders chosen for readability, not tuned.
- Line-of-sight uses integer Bresenham stepping between cell centers, vectorized via
  numpy for the per-step height comparison. Rock blocks sight via elevation exactly
  like any other terrain now -- there is no terrain-type special case anymore. A rock
  cell taller than the sightline blocks it; a rock cell shorter than the sightline does
  not. This was a deliberate removal of the previous "rock always blocks" shortcut.
- "Eye height" = cell elevation + a per-creature offset (default 1.0). Stairs/elevated
  ground raise this directly since they raise the cell's stored elevation.
- Performance: has_line_of_sight is O(distance) per call (a numpy-vectorized raycast,
  not Python-loop-per-cell). At many-agent scale the real cost is the O(N^2) number of
  pairs checked per tick, not the per-check cost. WorldGrid.elevation is a numpy array
  precisely so VisibilityMgr can slice it directly without a get()-per-cell loop.
  VisibilityMgr.has_line_of_sight applies a cheap max-range cull (squared-distance
  check, no sqrt) before doing any raycasting, which is the highest-leverage
  optimization for sparse worlds where most agent pairs are far apart. A true
  precomputed-visibility-set structure (recomputed only when terrain changes) would
  scale further but isn't built here -- add it only if profiling at your actual target
  agent count shows the cull + vectorization isn't enough.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
import numpy as np


class TerrainType(Enum):
    PLAIN = auto()
    ROCK = auto()        # impassable; also blocks LOS via elevation (see Cell.elevation)
    WATER = auto()        # passability depends on water_depth vs. creature's wade limit
    STAIRS = auto()        # passable; elevation determines vantage height


@dataclass
class Cell:
    terrain: TerrainType = TerrainType.PLAIN
    elevation: float = 0.0      # ground height; sea level = 0
    water_depth: float = 0.0    # 0 = dry. Only meaningful when terrain == WATER.


class WorldGrid:
    """2D array of Cells. (0,0) is the bottom-left corner by convention.

    Maintains a parallel numpy array of elevations (`elevation_map`) alongside the
    Cell objects, so VisibilityMgr can slice elevation data directly instead of calling
    get() per cell. The two stay in sync because set() is the only mutation path and it
    updates both. If you ever bypass set() to mutate a Cell's elevation in place,
    elevation_map will go stale -- there's no observer pattern here, by design, to keep
    this simple. Flagging this as the one sharp edge in this class.
    """

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._cells: list[list[Cell]] = [
            [Cell() for _ in range(height)] for _ in range(width)
        ]
        self.elevation_map: np.ndarray = np.zeros((width, height), dtype=np.float64)

    def get(self, x: int, y: int) -> Cell:
        if not self.in_bounds(x, y):
            raise IndexError(f"({x},{y}) is outside world bounds {self.width}x{self.height}")
        return self._cells[x][y]

    def set(self, x: int, y: int, cell: Cell) -> None:
        if not self.in_bounds(x, y):
            raise IndexError(f"({x},{y}) is outside world bounds {self.width}x{self.height}")
        self._cells[x][y] = cell
        self.elevation_map[x, y] = cell.elevation

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height


@dataclass
class CreatureMoveProfile:
    """Per-creature constants that affect terrain interaction.

    These are placeholders for whatever stat system the creature/agent module ends up
    using (e.g. derived from species, evolved genome, etc.) -- this class just defines
    the *interface* MovementResolver and VisibilityMgr depend on.
    """
    max_wade_depth: float = 0.0        # 0 = cannot enter any water; land-only creature
    eye_height_offset: float = 1.0
    base_move_cost: float = 1.0
    climb_cost_multiplier: float = 2.0  # energy cost per unit of elevation gained
    max_perception_range: float = 15.0  # cells; LOS auto-fails beyond this, no raycast
    max_shout_range: float = 25.0       # cells; comms range, independent of sight range
    max_climb_per_step: float = 2.0     # max elevation gain allowed in a single move step;
                                        # exceeding this makes the target cell impassable
                                        # regardless of terrain type. Set to math.inf to
                                        # allow unlimited climbing (e.g. flying creatures).


class VisibilityMgr:
    """Elevation-aware line-of-sight queries on a WorldGrid."""

    def __init__(self, world: WorldGrid):
        self.world = world

    def has_line_of_sight(
        self,
        origin: tuple[int, int],
        target: tuple[int, int],
        observer_profile: CreatureMoveProfile,
    ) -> bool:
        """True if `target` is visible from `origin`.

        Method: a cheap squared-distance cull runs first and rejects pairs beyond
        max_perception_range without doing any raycasting -- this is the main lever
        for many-agent performance, since most agent pairs in a sparse world are out
        of range and this check is O(1). For pairs within range, walk the Bresenham
        line between the two cells and compare, for every intermediate cell, its
        actual elevation against the height the unobstructed sight-line would have at
        that point (linear interpolation between observer eye height and target
        elevation). That comparison is vectorized across all intermediate cells at
        once via numpy rather than looped in Python.

        Terrain type no longer matters for this check by itself -- a ROCK cell blocks
        sight only if its elevation is tall enough, exactly like PLAIN or any other
        terrain. There is no terrain-type special case.
        """
        x0, y0 = origin
        x1, y1 = target

        dx_total = x1 - x0
        dy_total = y1 - y0
        squared_distance = dx_total * dx_total + dy_total * dy_total
        max_range = observer_profile.max_perception_range
        if squared_distance > max_range * max_range:
            return False  # out of perception range; no raycast performed

        if squared_distance == 0:
            return True  # origin == target

        origin_cell = self.world.get(x0, y0)
        eye_height = origin_cell.elevation + observer_profile.eye_height_offset
        target_height = self.world.elevation_map[x1, y1]

        xs, ys = self._bresenham_line_arrays(x0, y0, x1, y1)
        total_steps = len(xs) - 1  # xs/ys include both endpoints

        if total_steps <= 1:
            return True  # adjacent cells, nothing in between to occlude

        # Intermediate cells only (exclude both endpoints).
        mid_xs = xs[1:-1]
        mid_ys = ys[1:-1]
        mid_elevations = self.world.elevation_map[mid_xs, mid_ys]

        # Height the unobstructed sight-line has at each intermediate step.
        t = np.arange(1, total_steps) / total_steps
        sightline_heights = eye_height + t * (target_height - eye_height)

        return not np.any(mid_elevations > sightline_heights)

    @staticmethod
    def _bresenham_line_arrays(
        x0: int, y0: int, x1: int, y1: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """Standard integer Bresenham line, inclusive of both endpoints, as numpy arrays."""
        points: list[tuple[int, int]] = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x1 >= x0 else -1
        sy = 1 if y1 >= y0 else -1
        x, y = x0, y0

        if dx >= dy:
            err = dx // 2 if dx else 0
            for _ in range(dx + 1):
                points.append((x, y))
                err -= dy
                if err < 0:
                    y += sy
                    err += dx
                x += sx
            if points[-1] != (x1, y1):
                points.append((x1, y1))
        else:
            err = dy // 2 if dy else 0
            for _ in range(dy + 1):
                points.append((x, y))
                err -= dx
                if err < 0:
                    x += sx
                    err += dy
                y += sy
            if points[-1] != (x1, y1):
                points.append((x1, y1))

        xs = np.array([p[0] for p in points], dtype=np.intp)
        ys = np.array([p[1] for p in points], dtype=np.intp)
        return xs, ys


class MovementResolver:
    """Determines passability and energy cost of moving between adjacent cells."""

    def __init__(self, world: WorldGrid):
        self.world = world

    def can_pass(
        self,
        x: int,
        y: int,
        profile: CreatureMoveProfile,
        from_pos: tuple[int, int] | None = None,
    ) -> bool:
        """Return True if the creature can enter cell (x, y).

        from_pos is required to enforce max_climb_per_step; when omitted the
        climbing check is skipped (e.g. for spawn placement). This is the one
        footgun: callers that always omit from_pos will silently allow vertical
        teleportation, so the simulation's movement step always passes it.
        """
        cell = self.world.get(x, y)

        if cell.terrain == TerrainType.ROCK:
            return False

        if cell.terrain == TerrainType.WATER:
            if cell.water_depth > profile.max_wade_depth:
                return False

        if from_pos is not None:
            from_cell = self.world.get(*from_pos)
            elevation_gain = cell.elevation - from_cell.elevation
            if elevation_gain > profile.max_climb_per_step:
                return False

        return True

    def move_cost(
        self,
        from_pos: tuple[int, int],
        to_pos: tuple[int, int],
        profile: CreatureMoveProfile,
    ) -> float:
        """Energy cost to move from from_pos to to_pos (assumed adjacent).

        Cost = base movement cost + elevation-gain penalty (descending is not
        discounted in this version -- descending too fast could plausibly cost energy
        too in a later iteration, e.g. fall damage, but that's out of scope here).
        """
        if not self.can_pass(*to_pos, profile, from_pos=from_pos):
            raise ValueError(f"{to_pos} is not passable from {from_pos} for this creature profile")

        from_cell = self.world.get(*from_pos)
        to_cell = self.world.get(*to_pos)

        elevation_gain = max(0.0, to_cell.elevation - from_cell.elevation)
        cost = profile.base_move_cost + elevation_gain * profile.climb_cost_multiplier

        # Wading through water costs extra, proportional to depth, even if passable.
        if to_cell.terrain == TerrainType.WATER:
            cost += to_cell.water_depth * profile.base_move_cost

        return cost
