"""
BattleRunner: a battle of several rounds, with summed scores and a results table.

    runner = BattleRunner(BattleConfig(rounds=5, seed=1), [(Tracker, 2), (SpinBot, 2)])
    results = runner.run()
    print(results.table())

For step-by-step control (the viewer pauses and single-steps), drive it manually:

    while not runner.done:
        runner.start_round()
        while not runner.arena.over:
            frame = runner.step()
        runner.end_round()

Determinism: with a seed, terrain, spawns and the global `random` module (which
bots typically use) are seeded, so the same seed and bots give the same results,
provided no bot runs over its time budget. Timing is the one input that depends
on the machine, so tests and tournaments that need reproducibility should set
decide_time_budget_ms to None.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from terrabots import map_generator
from terrabots.battle.agent import BattleAgent
from terrabots.battle.arena import Arena
from terrabots.battle.config import BattleConfig, BotEntry
from terrabots.battle.isolation import ProcessBot, spec_of, start_bots
from terrabots.battle.storage import BotStorage
from terrabots.console import is_users_bot


def storage_key(cls: type) -> str:
    """Storage folder name for a bot class: its import path."""
    return f"{cls.__module__}.{cls.__qualname__}"
from terrabots.battle.scoring import BotScore
from terrabots.world_terrain import WorldGrid

RESULT_COLUMNS = ["rank", "name", "total", "survival", "last_survivor", "bullet_damage",
                  "bullet_kill_bonus", "ram_damage", "ram_kill_bonus", "firsts", "seconds",
                  "thirds", "shots", "hits", "hit_rate", "avg_end_energy", "skipped_turns"]


def load_bot_class(spec: str) -> type[BattleAgent]:
    """'package.module:ClassName' -> class. The working directory is importable, so
    bots in ./bots/ load the same way under `python -m` and the console script."""
    import importlib
    import os

    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    module_name, _, class_name = spec.partition(":")
    if not class_name:
        raise ValueError(f"bot spec {spec!r}: expected 'module:ClassName'")
    cls = getattr(importlib.import_module(module_name), class_name)
    if not (isinstance(cls, type) and issubclass(cls, BattleAgent)):
        raise ValueError(f"bot spec {spec!r}: {class_name} is not a BattleAgent subclass")
    return cls


def build_world(config: BattleConfig, rng: random.Random) -> WorldGrid:
    if config.terrain == "map":
        from terrabots import maps
        return maps.load(config.map)
    if config.terrain == "flat":
        return map_generator.flat(config.width, config.height)
    return map_generator.procedural(config.width, config.height, rng=rng)


@dataclass
class BattleResults:
    config: dict[str, Any]
    rows: list[dict[str, Any]]                       # sorted by total, rank 1 first
    rounds: list[dict[str, Any]] = field(default_factory=list)  # per-round rankings

    def to_json(self) -> str:
        return json.dumps({"config": self.config, "results": self.rows, "rounds": self.rounds},
                          indent=2)

    def to_csv(self) -> str:
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=RESULT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(self.rows)
        return out.getvalue()

    def save(self, directory: str | Path = "results") -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stem = time.strftime("%Y%m%d-%H%M%S")
        path = directory / f"{stem}.json"
        path.write_text(self.to_json(), encoding="utf-8")
        (directory / f"{stem}.csv").write_text(self.to_csv(), encoding="utf-8")
        return path

    def table(self) -> str:
        cols = [("rank", 4), ("name", 22), ("total", 8), ("survival", 8), ("bullet_damage", 8),
                ("ram_damage", 6), ("firsts", 4), ("seconds", 4), ("thirds", 4), ("hit_rate", 6)]
        heads = {"bullet_damage": "bullet", "ram_damage": "ram", "firsts": "1st",
                 "seconds": "2nd", "thirds": "3rd", "hit_rate": "hit%"}
        line = "  ".join(f"{heads.get(c, c):>{w}}" if c != "name" else f"{c:<{w}}" for c, w in cols)
        out = [line, "-" * len(line)]
        for r in self.rows:
            cells = []
            for c, w in cols:
                v = r[c]
                if c == "name":
                    cells.append(f"{v:<{w}}")
                elif c == "hit_rate":
                    cells.append(f"{v * 100:>{w}.1f}")
                elif isinstance(v, float):
                    cells.append(f"{v:>{w}.0f}")
                else:
                    cells.append(f"{v:>{w}}")
            out.append("  ".join(cells))
        return "\n".join(out)


class BattleRunner:
    def __init__(self, config: BattleConfig,
                 bots: list[tuple[type[BattleAgent], int]] | list[BotEntry],
                 time_budget_ms: float | None | str = "config",
                 on_round_start: Callable[[Arena], None] | None = None,
                 data_dir: str | None = None, console: bool = False) -> None:
        self.config = config
        self.console = console      # capture the user's bots' prints/logs for the viewer
        self.data_dir = data_dir    # bot storage root; None = in memory only
        self.entries: list[tuple[type[BattleAgent], int]] = [
            (load_bot_class(b.spec), b.count) if isinstance(b, BotEntry) else b for b in bots
        ]
        if sum(n for _, n in self.entries) < 2:
            raise ValueError("A battle needs at least two bots")

        # A debugger stepping through decide() would blow every time budget.
        if time_budget_ms == "config":
            time_budget_ms = None if sys.gettrace() is not None else config.decide_time_budget_ms
        self.time_budget_ms = time_budget_ms or None

        self.rng = random.Random(config.seed)
        if config.seed is not None:
            random.seed(config.seed)
        self.world = build_world(config, self.rng)
        self.memory: dict[type, dict[str, Any]] = {cls: {} for cls, _ in self.entries}
        self.round = 0
        self.arena: Arena | None = None
        self.arena_finished = True
        self.on_round_start = on_round_start

        self.names: list[tuple[type[BattleAgent], str]] = []
        for cls, count in self.entries:
            for i in range(count):
                self.names.append((cls, f"{cls.__name__} ({i + 1})" if count > 1 else cls.__name__))
        self.totals: dict[int, BotScore] = {
            bid: BotScore(name, cls.__name__) for bid, (cls, name) in enumerate(self.names)
        }
        self.round_rankings: list[dict[str, Any]] = []

        # One process per bot for the whole battle (bot_isolation = "process").
        self.processes: list[ProcessBot] = []
        if config.bot_isolation == "process":
            self.processes = start_bots([spec_of(cls) for cls, _ in self.names], self.world, config,
                                        data_dir)
        # One storage per bot class (in-process bots); process bots open their own.
        self.storages = {cls: BotStorage(data_dir, storage_key(cls), config.bot_storage_quota_kb)
                         for cls, _ in self.entries}

    def close(self) -> None:
        """Stop bot processes. Safe to call more than once."""
        for p in self.processes:
            p.close()
        self.processes = []

    def __enter__(self) -> "BattleRunner":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @property
    def done(self) -> bool:
        return self.round >= self.config.rounds and self.arena_finished

    def start_round(self) -> Arena:
        self.round += 1
        agents: list[BattleAgent] = []
        for bid, (cls, name) in enumerate(self.names):
            agent = self.processes[bid] if self.processes else cls()
            agent.bot_id, agent.name = bid, name
            agent.rules = dataclasses.replace(self.config)
            if not self.processes:
                agent.memory = self.memory[cls]
                agent.storage = self.storages[cls]
            agents.append(agent)
        console_ids = {bid for bid, (cls, _) in enumerate(self.names)
                       if self.console and is_users_bot(cls.__module__)}
        for bid in console_ids:
            if self.processes:
                self.processes[bid].console = True
        self.arena = Arena(self.config, self.world, agents, self.round, self.rng,
                           time_budget_ms=self.time_budget_ms, console_ids=console_ids)
        self.arena_finished = False
        for agent in agents:
            agent.on_round_start(self.round, self.config.rounds)
        if self.on_round_start:
            self.on_round_start(self.arena)
        return self.arena

    def step(self) -> dict[str, Any]:
        assert self.arena is not None
        frame = self.arena.step()
        frame["totals"] = {bid: round(self.totals[bid].total + self.arena.scorer.scores[bid].total, 1)
                           for bid in self.totals}
        return frame

    def end_round(self) -> list[dict[str, Any]]:
        """Score the finished round; returns its ranking rows (name, place, round score)."""
        assert self.arena is not None
        ranking = self.arena.finish()
        for bid, score in self.arena.scorer.scores.items():
            self.totals[bid].add(score)
        rows = [{"place": i + 1, "id": bid, "name": self.names[bid][1],
                 "score": round(self.arena.scorer.scores[bid].total, 1)}
                for i, bid in enumerate(ranking)]
        self.round_rankings.append({"round": self.round, "ticks": self.arena.tick, "ranking": rows})
        self.arena_finished = True
        return rows

    def results(self) -> BattleResults:
        ordered = sorted(self.totals.values(), key=lambda s: -s.total)
        rows = []
        for rank, s in enumerate(ordered, start=1):
            d = s.to_dict()
            d["rank"] = rank
            rows.append(d)
        return BattleResults(self.config.to_dict(), rows, self.round_rankings)

    def run(self, verbose: bool = False) -> BattleResults:
        try:
            return self._run(verbose)
        finally:
            self.close()

    def _run(self, verbose: bool) -> BattleResults:
        while self.round < self.config.rounds:
            arena = self.start_round()
            while not arena.over:
                self.step()
            ranking = self.end_round()
            if verbose:
                standing = len(arena.standing())
                outcome = (f"winner {ranking[0]['name']}" if standing == 1 else
                           f"time limit, {standing} left, leader {ranking[0]['name']}")
                print(f"Round {self.round}/{self.config.rounds}: {arena.tick} ticks, {outcome}")
        return self.results()
