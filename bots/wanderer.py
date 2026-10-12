"""
WandererAgent — the smallest useful bot, and the template for writing your own.

Copy this file to bots/my_bot.py, rename the class, and run it against the Wanderer:

    terrabots-run --agent bots.my_bot:MyBot=5 --agent bots.wanderer:WandererAgent=5

Or press F5 in VS Code and pick "Terrabots: Debug bots/wanderer" —
breakpoints inside decide() work.
"""

from terrabots.framework.actions import Action, MoveDirection
from terrabots.framework.agent import Agent
from terrabots.framework.observation import Observation


class WandererAgent(Agent):
    """Walk to the nearest visible food; otherwise wander randomly."""

    def decide(self, obs: Observation) -> Action:
        if obs.nearest_resource is not None:
            return Action(move_toward=obs.nearest_resource)
        return Action(move_direction=MoveDirection.RANDOM)
