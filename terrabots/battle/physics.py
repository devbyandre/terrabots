"""
Battle physics as plain functions on plain data: body kinematics, radar sweeps,
bullet flight. Kept free of bot objects and tick bookkeeping so each rule can be
tested on its own (tests/test_battle_physics.py).

Hybrid continuous-on-grid model (docs/arena-spec.md §2): bodies and bullets have
float positions; the cell under a point is (int(x), int(y)), and terrain rules
(passability, climb limit, elevation, LOS) are looked up on that cell.

Rules follow RoboWiki's Robocode/Game_Physics page: bodies are axis-aligned
squares (36 px = 2.25 cells by default) that don't rotate with the heading,
bullets are hit-tested as swept segments against those squares, and braking
through zero speed uses the leftover part of the tick to accelerate.
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
    as in Robocode, so stopping is quicker than starting. When a reversal reaches
    zero partway through the tick, the rest of the tick accelerates the other way.
    """
    target = clamp(target, -cfg.max_velocity, cfg.max_velocity)
    if v == target:
        return v
    if v * target < 0 and abs(v) < cfg.deceleration:
        leftover = 1.0 - abs(v) / cfg.deceleration
        return math.copysign(min(cfg.acceleration * leftover, abs(target)), target)
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


def footprint(x: float, y: float, half: float) -> tuple[int, int, int, int]:
    """Cell range (x_lo, x_hi, y_lo, y_hi), inclusive, under a body's square."""
    e = 1e-9  # an edge exactly on a cell boundary belongs to the cell inside the body
    return (math.floor(x - half), math.floor(x + half - e),
            math.floor(y - half), math.floor(y + half - e))


def blocked_reason(x0: float, y0: float, x1: float, y1: float, world: WorldGrid,
                   movement: MovementResolver, profile: CreatureMoveProfile,
                   half: float) -> str | None:
    """Why a body moving (x0, y0) -> (x1, y1) can't get there: "arena", "terrain" or None.

    Every cell the square newly covers must be enterable (rock, deep water) from
    the nearest cell it already covers (climb limit). A body is up to three cells
    wide, so checking only its corners would miss a rock under an edge.
    """
    if x1 < half or y1 < half or x1 > world.width - half or y1 > world.height - half:
        return "arena"
    ox_lo, ox_hi, oy_lo, oy_hi = footprint(x0, y0, half)
    nx_lo, nx_hi, ny_lo, ny_hi = footprint(x1, y1, half)
    for cx in range(nx_lo, nx_hi + 1):
        for cy in range(ny_lo, ny_hi + 1):
            if ox_lo <= cx <= ox_hi and oy_lo <= cy <= oy_hi:
                continue  # already under the body
            came_from = (min(max(cx, ox_lo), ox_hi), min(max(cy, oy_lo), oy_hi))
            if not movement.can_pass(cx, cy, profile, from_pos=came_from):
                return "terrain"
    return None


def footprint_passable(x: float, y: float, world: WorldGrid, movement: MovementResolver,
                       profile: CreatureMoveProfile, half: float) -> bool:
    """Spawn check: inside the arena, every covered cell enterable, ground not steeper
    than the climb limit anywhere under the body (or it would be stuck)."""
    if x < half or y < half or x > world.width - half or y > world.height - half:
        return False
    x_lo, x_hi, y_lo, y_hi = footprint(x, y, half)
    cells = [(cx, cy) for cx in range(x_lo, x_hi + 1) for cy in range(y_lo, y_hi + 1)]
    if not all(movement.can_pass(cx, cy, profile) for cx, cy in cells):
        return False
    heights = [world.elevation_map[c] for c in cells]
    return max(heights) - min(heights) <= profile.max_climb_per_step


def boxes_overlap(ax: float, ay: float, bx: float, by: float, half: float) -> bool:
    return abs(ax - bx) < 2 * half and abs(ay - by) < 2 * half


# ---------------------------------------------------------------------------
# Radar
# ---------------------------------------------------------------------------

def in_radar_arc(body: BattleBody, tx: float, ty: float, radius: float,
                 radar_range: float) -> bool:
    """Is a body of `radius` (its half width) at (tx, ty) inside the arc swept this tick?

    The arc runs from radar_prev by radar_sweep degrees. The target's angular size (its
    square's corners, as Robocode's arc-meets-bounding-box test) is
    added on both sides, so a radar that didn't turn still sees a bot it points
    straight at (needed for a locked radar).
    """
    d = distance(body.x, body.y, tx, ty)
    if d > radar_range + radius:
        return False
    if d <= radius * math.sqrt(2):
        return True
    # The target is an axis-aligned square (as in Robocode, whose radar arc must
    # touch the bot's bounding box): its angular extent spans its corners.
    # Corners relative to the target's centre first, so a target behind the sweep
    # (near +-180 degrees) can't wrap around into it.
    centre = heading_to(body.x, body.y, tx, ty)
    rel = normalize_angle(centre - body.radar_prev)
    offsets = [normalize_angle(heading_to(body.x, body.y, tx + sx * radius, ty + sy * radius) - centre)
               for sx in (-1, 1) for sy in (-1, 1)]
    lo, hi = min(0.0, body.radar_sweep), max(0.0, body.radar_sweep)
    return rel + min(offsets) <= hi and rel + max(offsets) >= lo


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
    line: tuple[float, float, float, float] | None = None   # its last move (x0, y0, x1, y1)


def segment_box_t(x0: float, y0: float, x1: float, y1: float,
                  cx: float, cy: float, half: float) -> float | None:
    """Smallest t in [0, 1] where segment P0→P1 enters the square, else None.

    Swept test (Liang–Barsky clipping) rather than a point test, so a fast bullet
    can't jump over a body.
    """
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - (cx - half)), (dx, (cx + half) - x0),
                 (-dy, y0 - (cy - half)), (dy, (cy + half) - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return t0


def segments_intersect_t(a0: tuple[float, float], a1: tuple[float, float],
                         b0: tuple[float, float], b1: tuple[float, float]) -> float | None:
    """t along segment A where it crosses segment B, else None (bullet–bullet hits)."""
    rx, ry = a1[0] - a0[0], a1[1] - a0[1]
    sx, sy = b1[0] - b0[0], b1[1] - b0[1]
    denom = rx * sy - ry * sx
    qx, qy = b0[0] - a0[0], b0[1] - a0[1]
    if abs(denom) < 1e-12:
        # Parallel. Collinear and overlapping is the head-on case (two bots aiming
        # straight at each other), which happens all the time.
        if abs(qx * ry - qy * rx) > 1e-9:
            return None
        rr = rx * rx + ry * ry
        if rr == 0:
            return None
        tb0 = (qx * rx + qy * ry) / rr
        tb1 = ((b1[0] - a0[0]) * rx + (b1[1] - a0[1]) * ry) / rr
        lo, hi = max(0.0, min(tb0, tb1)), min(1.0, max(tb0, tb1))
        return lo if lo <= hi else None
    t = (qx * sy - qy * sx) / denom
    u = (qx * ry - qy * rx) / denom
    return t if 0 <= t <= 1 and 0 <= u <= 1 else None


BULLET_RADIUS = 3 / 16     # cells; Robocode's bullet radius (3 px), for the arena edge


def terrain_block_t(x0: float, y0: float, x1: float, y1: float, z: float,
                    world: WorldGrid, step: float = 0.2) -> tuple[float, str] | None:
    """First t along the segment where the bullet hits ground higher than its flight
    height (same rule as LOS: terrain blocks by elevation), or leaves the arena.
    Robocode's rule for the arena edge: a bullet is gone once the end of its step is
    within BULLET_RADIUS of the edge (or beyond); then t = 1, the end of the step.
    """
    length = distance(x0, y0, x1, y1)
    n = max(1, math.ceil(length / step))
    for i in range(1, n + 1):
        t = i / n
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        cx, cy = math.floor(x), math.floor(y)
        if not world.in_bounds(cx, cy):
            break
        if world.elevation_map[cx, cy] > z:
            return t, "terrain"
    r = BULLET_RADIUS
    if not (r < x1 < world.width - r and r < y1 < world.height - r):
        return 1.0, "arena"
    return None


def bullet_next(bullet: Bullet) -> tuple[float, float]:
    return project(bullet.x, bullet.y, bullet.heading, bullet.speed)
