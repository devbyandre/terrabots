"""
Actions an agent can return from decide() each tick.

Design notes:
- One Action per tick; the simulation applies it atomically at the end of the tick
  after all agents have decided. This prevents order-of-iteration bugs.
- move_toward and move_direction are mutually exclusive; move_toward takes priority
  when both are set. move_direction=None means stay in place (costs only metabolism).
- shout is optional and independent of movement. An agent can move and communicate
  in the same tick.
- The Action dataclass is intentionally flat and simple now. Extend it here when new
  capability types are added (build, dig, eat, reproduce signal, etc.) rather than
  adding parallel action channels -- keep one action object per tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class MoveDirection(Enum):
    NORTH = (0, 1)
    SOUTH = (0, -1)
    EAST = (1, 0)
    WEST = (-1, 0)
    NORTH_EAST = (1, 1)
    NORTH_WEST = (-1, 1)
    SOUTH_EAST = (1, -1)
    SOUTH_WEST = (-1, -1)
    STAY = (0, 0)
    RANDOM = None  # resolved by simulation to a random passable adjacent cell

    def as_delta(self) -> tuple[int, int]:
        if self.value is None:
            raise ValueError("RANDOM must be resolved by the simulation before use")
        return self.value  # type: ignore[return-value]


@dataclass
class Shout:
    """An optional message broadcast attempt accompanying a move."""
    recipient_id: int
    kind: str                            # e.g. "danger", "food_found", "follow_me"
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    """What an agent wants to do this tick.

    Move resolution priority:
      1. move_toward (pos) -- simulation pathfinds one step toward the target cell
      2. move_direction    -- explicit direction; STAY = do not move
      3. neither set       -- equivalent to STAY

    shout: None = no comms this tick. Multiple shouts in one tick are not supported
    by design -- agents that need to broadcast to many recipients should do so over
    multiple ticks, trading off comms bandwidth against other actions.
    """
    move_toward: tuple[int, int] | None = None
    move_direction: MoveDirection | None = None
    shout: Shout | None = None
