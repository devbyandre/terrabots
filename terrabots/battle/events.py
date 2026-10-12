"""
Events a battle bot receives in its BattleObservation.

Events produced during tick N are delivered in the observation of tick N+1, the
same one-tick delay the survival mode uses for messages. Bearings are absolute
headings (0 = north, clockwise), not relative to the bot's body; subtract your own
heading with geometry.normalize_angle() to get a turn amount.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScannedBot:
    """Another bot swept by your radar this tick (in range and, by default, in LOS)."""
    bot_id: int
    name: str            # e.g. "Tracker (2)"
    class_name: str
    bearing: float       # absolute heading from you to it
    distance: float
    heading: float       # its body heading
    velocity: float
    energy: float
    elevation: float     # ground height under it


@dataclass(frozen=True)
class HitByBullet:
    shooter_id: int
    bearing: float       # direction the bullet came from
    power: float
    damage: float


@dataclass(frozen=True)
class BulletHit:
    target_id: int
    power: float
    damage: float
    target_energy: float  # target's energy after the hit


@dataclass(frozen=True)
class BulletMissed:
    power: float
    reason: str          # "terrain" or "arena"


@dataclass(frozen=True)
class HitWall:
    """You drove into the arena edge or a cell you can't enter (rock, steep, deep water)."""
    bearing: float
    damage: float


@dataclass(frozen=True)
class HitBot:
    bot_id: int
    bearing: float
    damage: float
    my_fault: bool       # True if your movement caused the collision (you rammed)


@dataclass(frozen=True)
class BotDeath:
    bot_id: int
    name: str
