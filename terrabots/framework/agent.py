"""
Abstract Agent base class.

To build an agent, subclass Agent and implement decide(). on_birth() and
on_message() are optional hooks. Everything else (energy, position, profile,
tick lifecycle) is managed by the Simulation.

Example minimal agent:

    from terrabots.framework.agent import Agent
    from terrabots.framework.actions import Action, MoveDirection
    from terrabots.framework.observation import Observation

    class WandererAgent(Agent):
        def decide(self, obs: Observation) -> Action:
            if obs.nearest_resource:
                return Action(move_toward=obs.nearest_resource)
            return Action(move_direction=MoveDirection.RANDOM)

Design notes:
- Agent subclasses own their internal state. The simulation only reads pos,
  energy, alive, and profile -- it never writes to agent internals beyond calling
  the lifecycle methods below.
- profile is a CreatureMoveProfile set at construction time. Agents with different
  species traits (different climb limits, eye height, wade depth) should pass a
  customised profile to super().__init__().
- agent_id is assigned by the Simulation at spawn time, not at construction.
  Avoid relying on it inside __init__ or on_birth(); it is guaranteed set before
  the first decide() call.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from terrabots.framework.actions import Action
    from terrabots.framework.observation import Observation

from terrabots.world_terrain import CreatureMoveProfile


class Agent(abc.ABC):
    """Base class for all Terrabots agents.

    Subclass this and implement decide(). The simulation calls the lifecycle
    methods in this order each tick:
        1. on_message(sender_id, kind, payload)  -- once per inbox message
        2. decide(obs) -> Action                 -- once; return your action
    And at construction:
        0. on_birth()                            -- after agent_id is assigned
    """

    def __init__(self, profile: CreatureMoveProfile | None = None) -> None:
        self.profile: CreatureMoveProfile = profile or CreatureMoveProfile()
        self.agent_id: int = -1           # set by Simulation before on_birth()
        self.pos: tuple[int, int] = (0, 0)
        self.energy: float = 100.0
        self.alive: bool = True

    # ------------------------------------------------------------------
    # Lifecycle hooks -- override as needed
    # ------------------------------------------------------------------

    def on_birth(self) -> None:
        """Called once after agent_id, pos, and energy are set by the Simulation.

        Use this to initialise internal state that depends on agent_id or the
        starting position. Do not call super().on_birth() -- the base is a no-op.
        """

    def on_message(self, sender_id: int, kind: str, payload: dict) -> None:
        """Called once per inbox message, before decide(), each tick.

        Convenience hook for agents that track comms state separately from their
        movement logic. The same messages are also available in obs.inbox inside
        decide(), so you can handle them in either place or both.
        """

    def on_death(self) -> None:
        """Called once when energy drops to zero or below.

        Use for cleanup or final stat logging. The agent is removed from the
        simulation after this call returns.
        """

    # ------------------------------------------------------------------
    # Core interface -- must implement
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def decide(self, obs: Observation) -> Action:
        """Return the action to take this tick.

        Called after on_message() for all inbox messages. The returned Action is
        applied by the Simulation at the end of the tick, after all agents have
        decided (no mid-tick state leakage between agents).
        """

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def x(self) -> int:
        return self.pos[0]

    @property
    def y(self) -> int:
        return self.pos[1]

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(id={self.agent_id}, "
            f"pos={self.pos}, energy={self.energy:.1f})"
        )
