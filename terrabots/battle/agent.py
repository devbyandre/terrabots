"""
BattleAgent: base class for Robocode-style battle bots.

Minimal bot:

    from terrabots.battle import BattleAction, BattleAgent, BattleObservation

    class SpinBot(BattleAgent):
        def decide(self, obs: BattleObservation) -> BattleAction:
            fire = 1.0 if obs.scanned_bots else 0.0
            return BattleAction(velocity=0.3, body_turn=5, radar_turn=45, fire=fire)

Design notes:
- Separate from the survival Agent on purpose: the two modes have different
  observations and actions, and one class with mode flags would be harder to read.
- A bot has three independent headings (body, gun, radar), as in Robocode. By
  default the gun turns along with the body and the radar along with the gun. Set
  adjust_gun_for_body_turn / adjust_radar_for_gun_turn = True on your class to
  make them independent (Robocode's setAdjustGunForRobotTurn etc.).
- `memory` is one dict per bot class that survives between rounds, the equivalent
  of Robocode static fields. Use it for statistics a learning bot carries over
  (GuessFactor histograms, hit rates). Every bot is re-created each round.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, ClassVar

from terrabots.world_terrain import CreatureMoveProfile

if TYPE_CHECKING:
    from terrabots.battle.actions import BattleAction
    from terrabots.battle.observation import BattleObservation


class BattleAgent(abc.ABC):
    adjust_gun_for_body_turn: ClassVar[bool] = False
    adjust_radar_for_gun_turn: ClassVar[bool] = False

    def __init__(self, profile: CreatureMoveProfile | None = None) -> None:
        self.profile: CreatureMoveProfile = profile or CreatureMoveProfile()
        self.bot_id: int = -1               # set by the arena before on_round_start()
        self.name: str = type(self).__name__
        self.memory: dict[str, Any] = {}    # replaced by the per-class battle memory

    def on_round_start(self, round_number: int, rounds: int) -> None:
        """Called once per round after bot_id, name and memory are set."""

    def on_death(self) -> None:
        """Called when this bot is destroyed."""

    def on_round_end(self, won: bool) -> None:
        """Called for every bot (alive or not) when the round ends."""

    @abc.abstractmethod
    def decide(self, obs: BattleObservation) -> BattleAction:
        """Return this tick's commands. All bots decide before anything moves."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.bot_id}, name={self.name!r})"
