"""
Survival runs for the browser viewer: settings, setup, frames and results.

The battle viewer's setup screen has a Survival tab; the server uses this module
to turn the form into a Simulation and to report it back. terrabots-run stays the
command-line way to run survival mode.
"""

from __future__ import annotations

import dataclasses
import math
import random
from dataclasses import dataclass
from typing import Any

from terrabots import map_generator
from terrabots.framework.agent import Agent
from terrabots.framework.simulation import ResourceConfig, SimConfig, Simulation


class SurvivalSettingsError(ValueError):
    """Invalid survival settings; the message names the field."""


_RANGES: dict[str, tuple[float, float | None]] = {
    "size": (16, 256), "max_ticks": (1, 1_000_000), "tick_delay_ms": (0, 5000),
    "initial_energy": (1, None), "metabolism_per_tick": (0, None),
    "initial_density": (0, 1), "max_per_cell": (1, None), "regen_rate": (0, None),
    "forage_amount": (0, None), "forage_cost": (0, None), "spawn_rate": (0, 100),
}


@dataclass
class SurvivalSettings:
    size: int = 48
    terrain: str = "procedural"          # "procedural" | "flat"
    seed: int | None = None
    max_ticks: int = 2000
    tick_delay_ms: int = 60
    initial_energy: float = 100.0
    metabolism_per_tick: float = 1.0
    initial_density: float = 0.05
    max_per_cell: float = 50.0
    regen_rate: float = 0.5
    forage_amount: float = 20.0
    forage_cost: float = 2.0
    spawn_rate: float = 0.3

    def __post_init__(self) -> None:
        if self.terrain not in ("procedural", "flat"):
            raise SurvivalSettingsError(f"terrain: {self.terrain!r} is not procedural or flat")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            raise SurvivalSettingsError(f"seed: expected an integer or null, got {self.seed!r}")
        for name, (lo, hi) in _RANGES.items():
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v):
                raise SurvivalSettingsError(f"{name}: expected a number, got {v!r}")
            if v < lo or (hi is not None and v > hi):
                raise SurvivalSettingsError(f"{name}: {v} outside [{lo}, {hi if hi is not None else '∞'}]")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurvivalSettings":
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise SurvivalSettingsError(f"{unknown[0]}: unknown setting")
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class SurvivalSession:
    """One survival run: the Simulation plus names and lifetimes for the viewer."""

    def __init__(self, settings: SurvivalSettings, entries: list[tuple[type[Agent], int]]) -> None:
        if sum(n for _, n in entries) < 1:
            raise ValueError("Pick at least one agent")
        self.settings = settings
        # Simulation uses the global random module (callers control reproducibility).
        random.seed(settings.seed)
        s = settings
        self.world = (map_generator.flat(s.size, s.size) if s.terrain == "flat"
                      else map_generator.procedural(s.size, s.size, rng=random))
        self.sim = Simulation(self.world, SimConfig(
            metabolism_per_tick=s.metabolism_per_tick, initial_energy=s.initial_energy,
            resource=ResourceConfig(initial_density=s.initial_density, max_per_cell=s.max_per_cell,
                                    regen_rate=s.regen_rate, forage_amount=s.forage_amount,
                                    forage_cost=s.forage_cost, spawn_rate=s.spawn_rate)))
        self.names: dict[int, str] = {}
        for cls, count in entries:
            for i, agent in enumerate(self.sim.add_agent(cls, count=count)):
                self.names[agent.agent_id] = f"{cls.__name__} ({i + 1})" if count > 1 else cls.__name__
        self.tick = 0
        self.died_at: dict[int, int] = {}
        self.pov: int | None = None     # viewer's fog of war: whose view to send

    @property
    def over(self) -> bool:
        return self.tick >= self.settings.max_ticks or not any(a.alive for a in self.sim._agents.values())

    def step(self) -> dict[str, Any]:
        snap = self.sim.step()
        self.tick = snap.tick
        for a in snap.agents:
            if not a["alive"] and a["id"] not in self.died_at:
                self.died_at[a["id"]] = snap.tick
        frame = {
            "type": "survival_tick", "tick": snap.tick, "n_alive": snap.n_alive,
            "messages": snap.n_messages_sent,
            "agents": [{"id": a["id"], "name": self.names[a["id"]], "class": a["class"],
                        "x": a["pos"][0], "y": a["pos"][1], "z": a["elevation"],
                        "energy": a["energy"], "alive": a["alive"]} for a in snap.agents],
            "resources": [[int(k.split(",")[0]), int(k.split(",")[1]), v]
                          for k, v in snap.resources.items()],
        }
        obs = self.sim.last_observations.get(self.pov) if self.pov is not None else None
        if obs is not None:
            w = self.world.width
            frame["pov"] = {
                "id": self.pov,
                "cells": [t.pos[1] * w + t.pos[0] for t in obs.visible_terrain],
                "agents": [a.agent_id for a in obs.visible_agents],
                "food": [list(r.pos) for r in obs.visible_resources],
            }
        return frame

    def agents_info(self) -> list[dict[str, Any]]:
        return [{"id": aid, "name": name, "class": type(self.sim._agents[aid]).__name__}
                for aid, name in self.names.items()]

    def results(self) -> list[dict[str, Any]]:
        """Per class: survivors, average lifetime and end energy; best first."""
        by_class: dict[str, dict[str, Any]] = {}
        for aid, agent in self.sim._agents.items():
            cls = type(agent).__name__
            row = by_class.setdefault(cls, {"class": cls, "count": 0, "alive": 0,
                                            "lifetime_sum": 0, "energy_sum": 0.0})
            row["count"] += 1
            row["alive"] += int(agent.alive)
            row["lifetime_sum"] += self.died_at.get(aid, self.tick)
            row["energy_sum"] += agent.energy if agent.alive else 0.0
        rows = []
        for row in by_class.values():
            n = row.pop("count")
            rows.append({**{k: v for k, v in row.items() if not k.endswith("_sum")},
                         "count": n, "avg_lifetime": round(row["lifetime_sum"] / n, 1),
                         "avg_end_energy": round(row["energy_sum"] / n, 1)})
        rows.sort(key=lambda r: (-r["alive"], -r["avg_lifetime"]))
        for rank, r in enumerate(rows, 1):
            r["rank"] = rank
        return rows
