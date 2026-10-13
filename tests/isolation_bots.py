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


class Remember(BattleAgent):
    """Counts the rounds it has played, across battles, in its storage."""

    def on_round_start(self, round_number, rounds):
        self.storage.save("count", self.storage.load("count", 0) + 1)

    def decide(self, obs):
        return BattleAction()


import logging as _logging

_log = _logging.getLogger(__name__)


class Chatty(BattleAgent):
    """Talks to its console: print, self.log and its module logger."""

    def decide(self, obs):
        if obs.tick == 2:
            print("hello from print")
            self.log("tick", obs.tick)
            _log.info("from the logger")
            _log.debug("too detailed, not shown")
        return BattleAction()
