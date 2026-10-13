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
    teammate: bool = False   # on your team (team battles); Robocode's isTeammate()


@dataclass(frozen=True)
class TeamMessage:
    """A message from a teammate, sent with broadcast() or send() last tick."""
    sender_id: int
    sender_name: str
    data: object         # plain data: dicts, lists, strings, numbers, bools, None


@dataclass(frozen=True)
class BulletFired:
    """Your shot from last tick left the gun (Robocode's setFireBullet() return value)."""
    bullet_id: int
    x: float
    y: float
    heading: float
    power: float
    speed: float         # cells/tick


@dataclass(frozen=True)
class HitByBullet:
    bullet_id: int
    shooter_id: int
    bearing: float       # direction the bullet came from
    power: float
    damage: float


@dataclass(frozen=True)
class BulletHit:
    bullet_id: int
    target_id: int
    power: float
    damage: float
    target_energy: float  # target's energy after the hit


@dataclass(frozen=True)
class BulletMissed:
    bullet_id: int
    power: float
    reason: str          # "terrain" or "arena"


@dataclass(frozen=True)
class BulletHitBullet:
    """Your bullet collided with another bullet; both are gone."""
    bullet_id: int
    other_bullet_id: int
    other_shooter_id: int


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
