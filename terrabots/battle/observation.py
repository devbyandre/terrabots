"""
BattleObservation: everything a battle bot knows at the start of a tick.

Perception rules (docs/arena-spec.md §5):
- Other bots are only known through radar (`scanned_bots`) and events. There is
  no 360° vision of bots.
- Terrain is static and visible within the bot's perception range, through the
  read-only `terrain` view. Unlike survival mode this does not LOS-check every
  cell; computing that per tick for every bot is the cost issue survival mode has,
  and for path planning knowing nearby ground heights is enough.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from terrabots.battle.events import (
    BotDeath,
    BulletFired,
    BulletHit,
    BulletHitBullet,
    BulletMissed,
    HitBot,
    HitByBullet,
    HitWall,
    ScannedBot,
)

if TYPE_CHECKING:
    from terrabots.comms import Message
    from terrabots.world_terrain import CreatureMoveProfile, MovementResolver, WorldGrid


class TerrainView:
    """Read-only, range-limited view of the arena terrain for one bot.

    Queries outside the bot's perception range (or outside the arena) return None.
    Cell coordinates are integers: the cell under a point (x, y) is (int(x), int(y)).
    """

    def __init__(self, world: WorldGrid, movement: MovementResolver,
                 profile: CreatureMoveProfile, x: float, y: float) -> None:
        self._world = world
        self._movement = movement
        self._profile = profile
        self._x, self._y = x, y
        self._range_sq = profile.max_perception_range ** 2

    def _visible(self, cx: int, cy: int) -> bool:
        if not self._world.in_bounds(cx, cy):
            return False
        dx, dy = cx + 0.5 - self._x, cy + 0.5 - self._y
        return dx * dx + dy * dy <= self._range_sq

    def elevation(self, cx: int, cy: int) -> float | None:
        return float(self._world.elevation_map[cx, cy]) if self._visible(cx, cy) else None

    def terrain(self, cx: int, cy: int) -> str | None:
        """TerrainType name: "PLAIN", "ROCK", "WATER" or "STAIRS"."""
        return self._world.get(cx, cy).terrain.name if self._visible(cx, cy) else None

    def passable(self, cx: int, cy: int, from_cell: tuple[int, int] | None = None) -> bool | None:
        """Can this bot enter the cell? Pass from_cell to include the climb limit."""
        if not self._visible(cx, cy):
            return None
        return self._movement.can_pass(cx, cy, self._profile, from_pos=from_cell)


@dataclass
class BattleObservation:
    # Time
    tick: int
    round: int                       # 1-based
    # Own state
    bot_id: int
    x: float
    y: float
    heading: float                   # body, degrees (0 = north, clockwise)
    gun_heading: float
    radar_heading: float
    velocity: float                  # cells/tick, negative when reversing
    energy: float
    gun_heat: float                  # can fire when this is 0
    elevation: float
    # Arena
    arena_width: int
    arena_height: int
    others: int                      # enemies still alive
    terrain: TerrainView | None = None
    # Events from the previous tick
    scanned_bots: list[ScannedBot] = field(default_factory=list)
    hit_by_bullet: list[HitByBullet] = field(default_factory=list)
    bullet_hit: list[BulletHit] = field(default_factory=list)
    bullet_missed: list[BulletMissed] = field(default_factory=list)
    bullet_fired: list[BulletFired] = field(default_factory=list)
    bullet_hit_bullet: list[BulletHitBullet] = field(default_factory=list)
    hit_wall: list[HitWall] = field(default_factory=list)
    hit_bot: list[HitBot] = field(default_factory=list)
    bot_death: list[BotDeath] = field(default_factory=list)
    skipped_turns: int = 0           # your turns skipped so far this round (too slow / errors)
    inbox: list[Message] = field(default_factory=list)

    @property
    def cell(self) -> tuple[int, int]:
        return int(self.x), int(self.y)

    def to_dict(self) -> dict[str, float]:
        """Flat numeric features for ML; the nearest scanned bot stands in for 'the enemy'."""
        nearest = min(self.scanned_bots, key=lambda s: s.distance, default=None)
        return {
            "tick": self.tick, "x": self.x, "y": self.y,
            "heading": self.heading, "gun_heading": self.gun_heading,
            "radar_heading": self.radar_heading, "velocity": self.velocity,
            "energy": self.energy, "gun_heat": self.gun_heat, "elevation": self.elevation,
            "others": self.others,
            "enemy_bearing": nearest.bearing if nearest else -1.0,
            "enemy_distance": nearest.distance if nearest else -1.0,
            "enemy_heading": nearest.heading if nearest else -1.0,
            "enemy_velocity": nearest.velocity if nearest else 0.0,
            "enemy_energy": nearest.energy if nearest else -1.0,
            "n_hit_by_bullet": len(self.hit_by_bullet),
            "n_hit_wall": len(self.hit_wall),
        }
