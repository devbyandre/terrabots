"""
Observation handed to an agent at the start of each tick's decide() call.

Design notes:
- Everything in Observation is a snapshot of the world as the agent can perceive it
  this tick. It does not include information the agent could not have derived from
  its own sensors (i.e. it is not omniscient). The simulation constructs this per
  agent before calling decide().
- visible_agents and visible_resources contain only cells within the agent's
  max_perception_range that also pass the LOS check, so the agent's decide() does
  not need to re-filter by range or LOS -- it's already done.
- inbox contains messages delivered last tick (i.e. after last tick's CommsMgr.deliver()
  and before CommsMgr.clear()). The agent sees them here rather than via on_message()
  so that decide() can react to comms and movement in the same call without needing
  to maintain inter-call state just to bridge the two.
- on_message() still exists on Agent as a convenience hook for agents that prefer to
  process comms separately from movement decisions (e.g. updating an internal map).
  The simulation calls it before decide() for each message in the inbox.
- This is intentionally Gymnasium-compatible: the simulation can expose obs as a dict
  for RL training without changing this class, by calling obs.to_dict().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from terrabots.comms import Message


@dataclass(frozen=True)
class AgentPercept:
    """What an agent can perceive about another visible agent."""
    agent_id: int
    pos: tuple[int, int]
    energy: float         # agents can see each other's energy level
    elevation: float      # elevation at their current cell


@dataclass(frozen=True)
class ResourcePercept:
    """A visible resource tile and how much food it currently holds."""
    pos: tuple[int, int]
    amount: float
    elevation: float


@dataclass(frozen=True)
class TerrainPercept:
    """A visible terrain cell (only cells within LOS range are included)."""
    pos: tuple[int, int]
    terrain_name: str     # TerrainType.name -- string so agents don't need to import
    elevation: float
    water_depth: float


@dataclass
class Observation:
    """Full observation handed to an agent at the start of each tick."""

    # Own state
    tick: int
    agent_id: int
    pos: tuple[int, int]
    energy: float
    elevation: float       # elevation of the agent's current cell

    # What the agent can perceive
    visible_agents: list[AgentPercept] = field(default_factory=list)
    visible_resources: list[ResourcePercept] = field(default_factory=list)
    visible_terrain: list[TerrainPercept] = field(default_factory=list)

    # Convenience: closest resource in LOS (None if none visible)
    nearest_resource: tuple[int, int] | None = None

    # Communication inbox (messages delivered at end of last tick)
    inbox: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Flat dict representation for RL frameworks (Gymnasium-style obs space)."""
        return {
            "tick": self.tick,
            "agent_id": self.agent_id,
            "pos_x": self.pos[0],
            "pos_y": self.pos[1],
            "energy": self.energy,
            "elevation": self.elevation,
            "n_visible_agents": len(self.visible_agents),
            "n_visible_resources": len(self.visible_resources),
            "nearest_resource_x": self.nearest_resource[0] if self.nearest_resource else -1,
            "nearest_resource_y": self.nearest_resource[1] if self.nearest_resource else -1,
            "n_inbox": len(self.inbox),
        }
