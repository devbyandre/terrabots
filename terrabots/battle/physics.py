"""
Battle physics as plain functions on plain data: body kinematics, radar sweeps,
bullet flight. Kept free of bot objects and tick bookkeeping so each rule can be
tested on its own (tests/test_battle_physics.py).

Hybrid continuous-on-grid model (docs/arena-spec.md §2): bodies and bullets have
float positions; the cell under a point is (int(x), int(y)), and terrain rules
(passability, climb limit, elevation, LOS) are looked up on that cell.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from terrabots.battle.config import BattleConfig
from terrabots.battle.geometry import clamp, distance, heading_to, normalize_angle, normalize_heading, project
from terrabots.world_terrain import CreatureMoveProfile, MovementResolver, WorldGrid

ALIVE, DISABLED, DEAD = "alive", "disabled", "dead"


@dataclass
class BattleBody:
    """Physical state of one tank. The arena owns these; bots only see copies."""
    bot_id: int
    x: float
    y: float
    heading: float = 0.0
    gun_heading: float = 0.0
    radar_heading: float = 0.0
    radar_prev: float = 0.0       # radar heading before this tick's turn (sweep start)
    radar_sweep: float = 0.0      # signed degrees turned this tick (sweep direction)
    velocity: float = 0.0
    energy: float = 100.0
    gun_heat: float = 0.0
    state: str = ALIVE            # alive | disabled (0 energy, can't act) | dead

    @property
    def cell(self) -> tuple[int, int]:
        return int(self.x), int(self.y)


# ---------------------------------------------------------------------------
# Kinematics
# ---------------------------------------------------------------------------

def next_velocity(v: float, target: float, cfg: BattleConfig) -> float:
    """Move v towards target, accelerating or braking at the configured rates.

    Braking (slowing down, or reversing direction) uses the faster deceleration,
    as in Robocode, so stopping is quicker than starting.
    """
    target = clamp(target, -cfg.max_velocity, cfg.max_velocity)
    if v == target:
        return v
    braking = v * target < 0 or abs(target) < abs(v)
    step = cfg.deceleration if braking else cfg.acceleration
    if target > v:
        return min(v + step, target)
    return max(v - step, target)


def apply_turns(body: BattleBody, body_turn: float, gun_turn: float, radar_turn: float,
                cfg: BattleConfig, adjust_gun: bool, adjust_radar: bool) -> None:
    """Turn body, gun and radar, each clamped to its own per-tick limit.

    Unless adjusted, the gun is carried by the body's turn and the radar by the
    gun's total turn (Robocode semantics).
    """
    limit = cfg.max_body_turn(body.velocity)
    b = clamp(body_turn, -limit, limit)
    g = clamp(gun_turn, -cfg.max_gun_turn_deg, cfg.max_gun_turn_deg)
    r = clamp(radar_turn, -cfg.max_radar_turn_deg, cfg.max_radar_turn_deg)

    gun_total = g + (0.0 if adjust_gun else b)
    radar_total = r + (0.0 if adjust_radar else gun_total)

    body.heading = normalize_heading(body.heading + b)
    body.gun_heading = normalize_heading(body.gun_heading + gun_total)
    body.radar_prev = body.radar_heading
    body.radar_heading = normalize_heading(body.radar_heading + radar_total)
    body.radar_sweep = radar_total


def blocked_reason(x: float, y: float, from_cell: tuple[int, int], world: WorldGrid,
                   movement: MovementResolver, profile: CreatureMoveProfile,
                   radius: float) -> str | None:
    """Why a body centred at (x, y) can't be there: "arena", "terrain", or None.

    Terrain is checked for the centre cell only (with the climb limit from the
    cell it comes from). At max 0.5 cells/tick a body cannot skip a cell.
    """
    if x < radius or y < radius or x > world.width - radius or y > world.height - radius:
        return "arena"
    cx, cy = int(x), int(y)
    if (cx, cy) != from_cell and not movement.can_pass(cx, cy, profile, from_pos=from_cell):
        return "terrain"
    return None


# ---------------------------------------------------------------------------
# Radar
# ---------------------------------------------------------------------------

def in_radar_arc(body: BattleBody, tx: float, ty: float, radius: float,
                 radar_range: float) -> bool:
    """Is a body of `radius` at (tx, ty) inside the arc swept this tick?

    The arc runs from radar_prev by radar_sweep degrees. The target's angular size is
    added on both sides, so a radar that didn't turn still sees a bot it points
    straight at (needed for a locked radar).
    """
    d = distance(body.x, body.y, tx, ty)
    if d > radar_range + radius:
        return False
    if d <= radius:
        return True
    half_width = math.degrees(math.asin(min(1.0, radius / d)))
    rel = normalize_angle(heading_to(body.x, body.y, tx, ty) - body.radar_prev)
    lo, hi = min(0.0, body.radar_sweep), max(0.0, body.radar_sweep)
    return lo - half_width <= rel <= hi + half_width


# ---------------------------------------------------------------------------
# Bullets
# ---------------------------------------------------------------------------

@dataclass
class Bullet:
    bullet_id: int
    shooter_id: int
    x: float
    y: float
    z: float           # flight height: shooter's ground + muzzle height, constant
    heading: float
    power: float
    speed: float


def segment_circle_t(x0: float, y0: float, x1: float, y1: float,
                     cx: float, cy: float, r: float) -> float | None:
    """Smallest t in [0, 1] where segment P0→P1 touches the circle, else None.

    Swept test rather than a point test, so a fast bullet can't jump over a body.
    """
    dx, dy = x1 - x0, y1 - y0
    fx, fy = x0 - cx, y0 - cy
    c = fx * fx + fy * fy - r * r
    if c <= 0:
        return 0.0  # starts inside
    a = dx * dx + dy * dy
    if a == 0:
        return None
    b = 2 * (fx * dx + fy * dy)
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    t = (-b - math.sqrt(disc)) / (2 * a)
    return t if 0.0 <= t <= 1.0 else None


def terrain_block_t(x0: float, y0: float, x1: float, y1: float, z: float,
                    world: WorldGrid, step: float = 0.2) -> tuple[float, str] | None:
    """First t along the segment where the bullet leaves the arena or hits ground
    higher than its flight height. Same rule as LOS: terrain blocks by elevation.
    """
    length = distance(x0, y0, x1, y1)
    n = max(1, math.ceil(length / step))
    for i in range(1, n + 1):
        t = i / n
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        cx, cy = math.floor(x), math.floor(y)
        if not world.in_bounds(cx, cy):
            return t, "arena"
        if world.elevation_map[cx, cy] > z:
            return t, "terrain"
    return None


def bullet_next(bullet: Bullet) -> tuple[float, float]:
    return project(bullet.x, bullet.y, bullet.heading, bullet.speed)
