"""Grazer: a survival-mode demo agent. Eats a cell empty before moving on, and
heads for the richest visible food rather than the nearest."""

from terrabots.framework.actions import Action, MoveDirection
from terrabots.framework.agent import Agent
from terrabots.framework.observation import Observation

STILL_WORTH_IT = 3.0   # eating costs 2 energy per tick, so leave below this


class Grazer(Agent):
    """Stays on food until it's eaten; goes for the richest food in sight."""

    def decide(self, obs: Observation) -> Action:
        here = next((r for r in obs.visible_resources if r.pos == obs.pos), None)
        if here is not None and here.amount > STILL_WORTH_IT:
            return Action(move_direction=MoveDirection.STAY)
        if obs.visible_resources:
            best = max(obs.visible_resources,
                       key=lambda r: r.amount / (1 + abs(r.pos[0] - obs.pos[0]) + abs(r.pos[1] - obs.pos[1])))
            return Action(move_toward=best.pos)
        return Action(move_direction=MoveDirection.RANDOM)
