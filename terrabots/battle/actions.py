"""
BattleAction: what a battle bot wants to do this tick.

Each field is a per-tick command, clamped by the arena's rules (max turn rates, max
speed, bullet power range). Unlike Robocode there are no blocking calls such as
ahead(100): a bot that wants to drive 100 cells keeps returning a velocity until
it has. That keeps decide() a pure function of the observation, which is what ML
policies need.
"""

from __future__ import annotations

from dataclasses import dataclass

from terrabots.framework.actions import Shout


@dataclass
class BattleAction:
    velocity: float = 0.0     # desired speed in cells/tick; negative = reverse.
                              # Reached gradually (acceleration/deceleration limits).
    body_turn: float = 0.0    # degrees, + = clockwise; clamped by speed-dependent limit
    gun_turn: float = 0.0     # degrees; clamped to max_gun_turn_deg
    radar_turn: float = 0.0   # degrees; clamped to max_radar_turn_deg
    fire: float = 0.0         # bullet power; 0 = don't fire. Ignored while gun is hot.
    shout: Shout | None = None  # message to another bot (needs comms_enabled + LOS)
    fire_heading: float | None = None   # Robocode's fire assistance, for plain_robot bots only:
                              # aim straight at a bot scanned this tick (gun and radar aligned)
    scan: bool = False        # scan this tick even if nothing moves (Robocode's scan()):
                              # a tank that neither moves nor turns doesn't scan otherwise
