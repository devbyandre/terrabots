"""LevyForager: survival agent for the "search" level of the survival guide.

When it sees no food it searches with a Lévy flight: straight runs in random
directions whose lengths follow a power law (many short runs, a few very long
ones). Viswanathan et al. (1999) showed that this beats a plain random walk when
food is sparse and patchy, because the long runs carry the searcher into new
areas instead of re-visiting the same neighbourhood. Food in sight: it grazes
like Grazer.
"""

import random

from terrabots.framework.actions import Action, MoveDirection
from terrabots.framework.agent import Agent
from terrabots.framework.observation import Observation

MU = 2.0            # power-law exponent; ~2 is the optimum for sparse food in the paper
MAX_RUN = 40        # longest run in cells (the world is finite)
STILL_WORTH_IT = 3.0
DIRECTIONS = [d for d in MoveDirection if d not in (MoveDirection.STAY, MoveDirection.RANDOM)]


def levy_run_length(rng: random.Random) -> int:
    """Run length with P(l) ~ l^-MU for l >= 1 (inverse-transform sampling)."""
    u = 1.0 - rng.random()
    return min(MAX_RUN, int(u ** (-1.0 / (MU - 1.0))))


class LevyForager(Agent):
    """Grazes food in sight; otherwise searches with Lévy-flight runs."""

    def on_birth(self) -> None:
        self.rng = random.Random(self.agent_id)
        self.direction = self.rng.choice(DIRECTIONS)
        self.steps_left = 0
        self.last_pos = None

    def decide(self, obs: Observation) -> Action:
        here = next((r for r in obs.visible_resources if r.pos == obs.pos), None)
        if here is not None and here.amount > STILL_WORTH_IT:
            return Action(move_direction=MoveDirection.STAY)
        if obs.visible_resources:
            best = max(obs.visible_resources,
                       key=lambda r: r.amount / (1 + abs(r.pos[0] - obs.pos[0]) + abs(r.pos[1] - obs.pos[1])))
            self.steps_left = 0
            return Action(move_toward=best.pos)
        blocked = self.last_pos == obs.pos          # didn't move last tick: terrain or edge
        if self.steps_left <= 0 or blocked:
            self.direction = self.rng.choice(DIRECTIONS)
            self.steps_left = levy_run_length(self.rng)
        self.steps_left -= 1
        self.last_pos = obs.pos
        return Action(move_direction=self.direction)
