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
- `rules` is the battle's BattleConfig (Robocode's Rules class plus the battle
  settings): bullet_speed(power), damage(power), gun_cooling_rate, max_velocity...
  It's a copy; changing it changes nothing.
- `draw` is a DebugCanvas for graphical debugging (Robocode's onPaint).
- `storage` (Robocode's data directory): small JSON files that survive between
  battles, per bot class, within a size quota. See terrabots.battle.storage.
- `colors` (Robocode's setColors): CSS colours for "body", "gun", "radar",
  "bullet" and "scan" (the radar wedge). Set them in on_round_start(); any
  left out use the bot's default colour.

Teams (Robocode's TeamRobot and Droid):
- `team` is your team's name (None when you fight alone), `teammates` maps the
  other members' bot ids to names, `is_leader` is True for the team's first
  member (it starts with extra energy).
- `broadcast(data)` sends to every teammate, `send(to, data)` to one (bot id or
  name). Messages arrive in the next tick's `obs.team_messages`. Data must be
  JSON-like (dicts, lists, strings, numbers) and at most MAX_MESSAGE_BYTES.
- Set `droid = True` on a class for a Droid: extra energy but no radar, so it
  sees only through its teammates' messages.
"""

from __future__ import annotations

import abc
import json
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from terrabots.battle.config import BattleConfig
from terrabots.battle.debug import DebugCanvas
from terrabots.battle.storage import BotStorage
from terrabots.world_terrain import CreatureMoveProfile

if TYPE_CHECKING:
    from terrabots.battle.actions import BattleAction
    from terrabots.battle.observation import BattleObservation


logger = logging.getLogger(__name__)

MAX_MESSAGE_BYTES = 4096        # per message, as JSON
MAX_MESSAGES_PER_TICK = 10


class BattleAgent(abc.ABC):
    adjust_gun_for_body_turn: ClassVar[bool] = False
    adjust_radar_for_gun_turn: ClassVar[bool] = False
    droid: ClassVar[bool] = False   # Robocode Droid: more energy, no radar
    plain_robot: ClassVar[bool] = False  # Robocode's Robot (not AdvancedRobot): no wall damage, fire assistance

    def __init__(self, profile: CreatureMoveProfile | None = None) -> None:
        self.profile: CreatureMoveProfile = profile or CreatureMoveProfile()
        self.bot_id: int = -1               # set by the arena before on_round_start()
        self.name: str = type(self).__name__
        self.memory: dict[str, Any] = {}    # replaced by the per-class battle memory
        self.storage = BotStorage(None, type(self).__name__)   # replaced by the battle's
        self.rules: BattleConfig = BattleConfig()   # replaced by the battle's rules
        self.draw = DebugCanvas()
        self.colors: dict[str, str] = {}
        self._console: list[str] = []
        self.team: str | None = None            # set by the runner in team battles
        self.teammates: dict[int, str] = {}     # bot id -> name, without yourself
        self.is_leader = False
        self._outbox: list[tuple[int | None, object]] = []   # (recipient or None = all, data)

    # --- teams -----------------------------------------------------------

    def is_teammate(self, bot: int | str) -> bool:
        """Robocode's isTeammate(): by bot id or name."""
        return bot in self.teammates or bot in self.teammates.values()

    def broadcast(self, data: object) -> None:
        """Send `data` to all teammates; they read it next tick in obs.team_messages."""
        self._queue_message(None, data)

    def send(self, to: int | str, data: object) -> None:
        """Send `data` to one teammate, by bot id or name."""
        bot_id = to if isinstance(to, int) else next((i for i, n in self.teammates.items() if n == to), None)
        if bot_id not in self.teammates:
            logger.warning("%s: send() to %r, which isn't a teammate; dropped", self.name, to)
            return
        self._queue_message(bot_id, data)

    def _queue_message(self, to: int | None, data: object) -> None:
        if len(self._outbox) >= MAX_MESSAGES_PER_TICK:
            logger.warning("%s: more than %d messages this tick; dropped", self.name, MAX_MESSAGES_PER_TICK)
            return
        try:
            text = json.dumps(data)
        except (TypeError, ValueError):
            logger.warning("%s: message isn't plain data (dicts, lists, str, numbers); dropped", self.name)
            return
        if len(text) > MAX_MESSAGE_BYTES:
            logger.warning("%s: message of %d bytes is over %d; dropped", self.name, len(text), MAX_MESSAGE_BYTES)
            return
        # A JSON copy, so the receiver can't share objects with the sender.
        self._outbox.append((to, json.loads(text)))

    def take_outbox(self) -> list[tuple[int | None, object]]:
        """Messages queued during this decide(); the arena collects them."""
        out, self._outbox = self._outbox, []
        return out


    def log(self, *parts: object) -> None:
        """Write a line to this bot's console in the viewer (like print())."""
        if len(self._console) < 200:
            self._console.append(" ".join(str(p) for p in parts))

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
