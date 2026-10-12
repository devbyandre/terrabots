"""Misbehaving bots for tests/test_battle_isolation.py (must be importable by spec)."""

import time

from terrabots.battle import BattleAction, BattleAgent


class Hang(BattleAgent):
    """Never returns from decide() after the first few turns."""

    def decide(self, obs):
        if obs.tick > 3:
            while True:
                time.sleep(1)
        return BattleAction()


class Boom(BattleAgent):
    def decide(self, obs):
        raise RuntimeError("boom")


class Counter(BattleAgent):
    def on_round_start(self, round_number, rounds):
        self.memory["rounds"] = self.memory.get("rounds", 0) + 1

    def decide(self, obs):
        # Report what the process-local memory holds through a debug drawing.
        self.draw.text(0, 0, str(self.memory["rounds"]))
        return BattleAction()
