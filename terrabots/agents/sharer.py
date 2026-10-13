"""Sharer: survival agent for the "communication" level of the survival guide.

Grazes like Grazer, but when it finds a rich food cell it tells a creature it
can see (one message per tick, which must be in shout range and line of sight),
and when it has no food in sight it follows the tips it received. Information
sharing helps a group find patchy food faster (social foraging); it also helps
competitors, which is the producer–scrounger trade-off (Barnard & Sibly 1981).
"""

from terrabots.framework.actions import Action, MoveDirection, Shout
from terrabots.framework.agent import Agent
from terrabots.framework.observation import Observation

RICH = 20.0
STILL_WORTH_IT = 3.0


class Sharer(Agent):
    """Grazes; shares rich food finds with creatures it can see; follows tips."""

    def on_birth(self) -> None:
        self.tips: list[tuple[int, int]] = []
        self.told: set[int] = set()

    def on_message(self, sender_id: int, kind: str, payload: dict) -> None:
        if kind == "food" and "pos" in payload:
            self.tips.append(tuple(payload["pos"]))

    def decide(self, obs: Observation) -> Action:
        shout = None
        rich = [r for r in obs.visible_resources if r.amount >= RICH]
        listeners = [a for a in obs.visible_agents if a.agent_id not in self.told]
        if rich and listeners:
            to = listeners[0].agent_id
            self.told.add(to)
            shout = Shout(recipient_id=to, kind="food", payload={"pos": list(rich[0].pos)})

        here = next((r for r in obs.visible_resources if r.pos == obs.pos), None)
        if here is not None and here.amount > STILL_WORTH_IT:
            return Action(move_direction=MoveDirection.STAY, shout=shout)
        if obs.visible_resources:
            best = max(obs.visible_resources,
                       key=lambda r: r.amount / (1 + abs(r.pos[0] - obs.pos[0]) + abs(r.pos[1] - obs.pos[1])))
            return Action(move_toward=best.pos, shout=shout)
        while self.tips and self.tips[-1] == obs.pos:
            self.tips.pop()
        if self.tips:
            return Action(move_toward=self.tips[-1], shout=shout)
        return Action(move_direction=MoveDirection.RANDOM, shout=shout)
