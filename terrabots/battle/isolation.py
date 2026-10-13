"""
Run each bot in its own process (BattleConfig.bot_isolation = "process").

Why: a bot is arbitrary Python. In-process, a bot that loops forever freezes the
battle and a crashing one can corrupt shared state. In its own process a bot
can be killed after a hard time limit, can't touch the engine's objects, and
all bots compute their turns in parallel.

How: the arena talks to a ProcessBot proxy, which looks like a BattleAgent. The
child process imports the bot by spec ("module:Class"), keeps a copy of the
terrain, and answers one message per call over a Pipe. Observations are plain
dataclasses, so they pickle as they are; the terrain view is rebuilt in the child.

Differences from in-process bots:
- `memory` lives in the bot's process, so two bots of the same class no longer
  share it. That's how Robocode works too (one classloader per robot).
- The global `random` module is seeded per bot (seed + bot id), so a seeded battle
  is reproducible, but gives different results than the same seed in-process.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import random
import time
import traceback
from multiprocessing.connection import Connection
from typing import Any

from terrabots.battle.actions import BattleAction
from terrabots.battle.agent import BattleAgent
from terrabots.battle.config import BattleConfig
from terrabots.battle.observation import BattleObservation, TerrainView
from terrabots.console import capture
from terrabots.world_terrain import MovementResolver, WorldGrid

logger = logging.getLogger(__name__)

START_TIMEOUT_S = 30.0       # importing a heavy bot (torch...) can take a while
HARD_TIMEOUT_MIN_S = 2.0     # a turn longer than this (or 20x the budget) kills the bot


class BotProcessError(RuntimeError):
    """The bot's process failed, timed out hard, or raised in a hook."""


def spec_of(cls: type) -> str:
    """'module:Class' for a class, if a fresh process can import it."""
    if cls.__module__ == "__main__" or "<locals>" in cls.__qualname__:
        raise ValueError(f"{cls.__qualname__}: bot_isolation='process' needs a bot defined at "
                         f"module level in an importable file, not in __main__ or a function")
    return f"{cls.__module__}:{cls.__qualname__}"


# ---------------------------------------------------------------------------
# Child side
# ---------------------------------------------------------------------------

def _child_main(conn: Connection, spec: str, world: WorldGrid, seed: int | None, cwd: str,
                data_dir: str | None = None, quota_kb: int = 200) -> None:
    import os
    import sys

    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    os.chdir(cwd)
    from terrabots.battle.runner import load_bot_class

    if seed is not None:
        random.seed(seed)
    movement = MovementResolver(world)
    try:
        cls = load_bot_class(spec)
    except Exception:
        conn.send(("error", traceback.format_exc()))
        return
    conn.send(("ready", cls.__name__))
    memory: dict[str, Any] = {}
    from terrabots.battle.runner import storage_key
    from terrabots.battle.storage import BotStorage

    storage = BotStorage(data_dir, storage_key(cls), quota_kb)
    agent: BattleAgent | None = None

    while True:
        try:
            msg = conn.recv()
        except EOFError:
            return
        kind = msg[0]
        try:
            if kind == "round":
                _, bot_id, name, rules, round_number, rounds, console = msg
                agent = cls()
                agent.bot_id, agent.name, agent.memory, agent.rules = bot_id, name, memory, rules
                agent.storage = storage
                agent.on_round_start(round_number, rounds)
                conn.send(("ok", agent.adjust_gun_for_body_turn, agent.adjust_radar_for_gun_turn,
                           agent.profile, agent.colors))
            elif kind == "decide":
                _, seq, obs = msg
                assert agent is not None
                obs.terrain = TerrainView(world, movement, agent.profile, obs.x, obs.y)
                agent.draw.clear()
                start = time.perf_counter()
                with capture(agent, console) as lines:
                    action = agent.decide(obs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                if not isinstance(action, BattleAction):
                    raise TypeError(f"decide() returned {type(action).__name__}, expected BattleAction")
                conn.send(("action", seq, action, agent.draw.shapes, elapsed_ms,
                           agent.adjust_gun_for_body_turn, agent.adjust_radar_for_gun_turn, lines))
            elif kind == "death":
                if agent is not None:
                    agent.on_death()
            elif kind == "round_end":
                if agent is not None:
                    agent.on_round_end(won=msg[1])
            elif kind == "stop":
                return
        except Exception:
            if kind == "decide":
                conn.send(("decide_error", msg[1], traceback.format_exc()))
            elif kind == "round":
                conn.send(("error", traceback.format_exc()))
            else:
                logger.warning("bot %s raised in %s:\n%s", spec, kind, traceback.format_exc())


# ---------------------------------------------------------------------------
# Parent side
# ---------------------------------------------------------------------------

class ProcessBot(BattleAgent):
    """Arena-facing proxy for a bot running in its own process."""

    def __init__(self, spec: str, world: WorldGrid, seed: int | None,
                 data_dir: str | None = None, quota_kb: int = 200) -> None:
        super().__init__()
        import os

        self.spec = spec
        self.class_name = spec.rpartition(":")[2]
        ctx = mp.get_context("spawn")   # safe with the viewer's threads; same on every OS
        self._conn, child = ctx.Pipe()
        self._proc = ctx.Process(target=_child_main, args=(child, spec, world, seed, os.getcwd(), data_dir, quota_kb),
                                 daemon=True, name=f"bot:{spec}")
        self._proc.start()
        child.close()
        self._seq = 0
        self._dead = False
        self.last_elapsed_ms = 0.0
        self.console = False          # capture prints/logs (set by the runner)
        self.last_console: list[str] = []

    @property
    def is_dead(self) -> bool:
        return self._dead

    def wait_ready(self) -> None:
        reply = self._recv(START_TIMEOUT_S, "start")
        if reply[0] != "ready":
            self.close()
            raise BotProcessError(f"{self.spec} failed to load:\n{reply[1]}")
        self.class_name = reply[1]

    # --- lifecycle hooks -------------------------------------------------

    def on_round_start(self, round_number: int, rounds: int) -> None:
        self._send(("round", self.bot_id, self.name, self.rules, round_number, rounds, self.console))
        reply = self._recv(START_TIMEOUT_S, "on_round_start")
        if reply[0] != "ok":
            raise BotProcessError(f"{self.name} failed in on_round_start:\n{reply[1]}")
        _, self.adjust_gun_for_body_turn, self.adjust_radar_for_gun_turn, self.profile, self.colors = reply

    def on_death(self) -> None:
        self._send(("death",))

    def on_round_end(self, won: bool) -> None:
        self._send(("round_end", won))

    # --- decide: split in request/collect so all bots think in parallel ---

    def request_decide(self, obs: BattleObservation) -> None:
        if self._dead:
            return
        self._seq += 1
        obs.terrain = None   # rebuilt in the child from its own copy of the world
        self._send(("decide", self._seq, obs))

    def collect_decide(self, budget_ms: float | None) -> BattleAction:
        """The action for the last request. Raises on errors and on a hard timeout
        (the process is killed); a soft timeout is the arena's business."""
        if self._dead:
            raise BotProcessError(f"{self.name}'s process is gone")
        hard = max(HARD_TIMEOUT_MIN_S, 20 * (budget_ms or 0) / 1000)
        deadline = time.monotonic() + hard
        while True:
            reply = self._recv(max(0.0, deadline - time.monotonic()), "decide")
            if reply[1] != self._seq:
                continue  # stale answer from a turn we already gave up on
            if reply[0] == "decide_error":
                raise BotProcessError(reply[2])
            _, _, action, shapes, self.last_elapsed_ms, adj_gun, adj_radar, self.last_console = reply
            self.draw.shapes = shapes
            self.adjust_gun_for_body_turn, self.adjust_radar_for_gun_turn = adj_gun, adj_radar
            return action

    def decide(self, obs: BattleObservation) -> BattleAction:
        self.request_decide(obs)
        return self.collect_decide(None)

    # --- plumbing -------------------------------------------------------

    def _send(self, msg: tuple) -> None:
        if self._dead:
            return
        try:
            self._conn.send(msg)
        except (BrokenPipeError, OSError):
            self._kill("pipe closed")

    def _recv(self, timeout: float, what: str) -> tuple:
        if self._dead or not self._conn.poll(timeout):
            self._kill(f"no answer to {what} within {timeout:.1f}s")
            raise BotProcessError(f"{self.name}: no answer to {what} within {timeout:.1f}s; process killed")
        try:
            return self._conn.recv()
        except (EOFError, OSError) as exc:
            self._kill("process exited")
            raise BotProcessError(f"{self.name}: process exited") from exc

    def _kill(self, reason: str) -> None:
        if not self._dead:
            logger.warning("Stopping %s (%s): %s", self.name, self.spec, reason)
        self._dead = True
        if self._proc.is_alive():
            self._proc.kill()

    def close(self) -> None:
        if not self._dead:
            try:
                self._conn.send(("stop",))
            except (BrokenPipeError, OSError):
                pass
            self._proc.join(timeout=1.0)
        if self._proc.is_alive():
            self._proc.kill()
        self._dead = True
        self._conn.close()


def start_bots(specs: list[str], world: WorldGrid, config: BattleConfig,
               data_dir: str | None = None) -> list[ProcessBot]:
    """Start one process per bot in parallel and wait until all have loaded."""
    bots = [ProcessBot(spec, world, None if config.seed is None else config.seed + i,
                       data_dir, config.bot_storage_quota_kb)
            for i, spec in enumerate(specs)]
    try:
        for b in bots:
            b.wait_ready()
    except BotProcessError:
        for b in bots:
            b.close()
        raise
    return bots
