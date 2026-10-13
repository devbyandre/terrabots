"""
BattleConfig: every tunable rule of a battle, loadable from TOML.

Units: one cell = one distance unit. Robocode measures in pixels; its reference
values are converted with PX_PER_CELL = 16, so Robocode's max speed of 8 px/tick
becomes 0.5 cells/tick. Robocode values are from general knowledge of its rules,
not checked against its source; see docs/arena-spec.md §3.

A battle file holds the config fields at top level plus the bots to fight:

    rounds = 5
    seed = 42
    [[bots]]
    spec = "terrabots.agents.tracker:Tracker"
    count = 2

and, for team battles, teams (the first member is the leader):

    [[teams]]
    name = "Red"
    [[teams.members]]
    spec = "terrabots.agents.squad:SquadLeader"
    [[teams.members]]
    spec = "terrabots.agents.squad:SquadDroid"
    count = 2
"""

from __future__ import annotations

import dataclasses
import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PX_PER_CELL = 16.0

_CHOICES: dict[str, tuple[str, ...]] = {
    "terrain": ("procedural", "flat", "map"),
    "damage_formula": ("robocode", "linear"),
    "hit_energy_return": ("damage", "robocode", "none"),
    "bot_isolation": ("none", "process"),
}

# (min, max) inclusive; None = unbounded on that side.
_RANGES: dict[str, tuple[float | None, float | None]] = {
    "width": (16, 256),
    "height": (16, 256),
    "rounds": (1, 1000),
    "max_ticks_per_round": (1, 1_000_000),
    "tick_delay_ms": (0, 5000),
    "initial_energy": (1, None),
    "max_velocity": (0.01, 5),
    "acceleration": (0.001, 5),
    "deceleration": (0.001, 5),
    "max_body_turn_deg": (0, 180),
    "body_turn_velocity_penalty": (0, None),
    "max_gun_turn_deg": (0, 180),
    "max_radar_turn_deg": (0, 180),
    "body_half_width": (0.05, 4),
    "inactivity_time": (0, None),
    "inactivity_energy_drain": (0, None),
    "min_bullet_power": (0.01, None),
    "max_bullet_power": (0.01, None),
    "bullet_speed_fixed": (0.01, 10),
    "max_bullet_speed": (0.01, 10),
    "damage_per_power": (0, None),
    "max_damage": (0, None),
    "initial_gun_heat": (0, None),
    "gun_cooling_rate": (0.001, None),
    "radar_range": (1, 1000),
    "ram_damage": (0, None),
    "decide_time_budget_ms": (0, None),
    "bot_storage_quota_kb": (0, 10240),
    "team_leader_bonus": (0, None),
    "droid_bonus": (0, None),
    "team_message_range": (1, 1000),
}
MAX_TEAMS = 8
MAX_TEAM_NAME = 24


class BattleConfigError(ValueError):
    """Invalid battle configuration; the message names the offending field."""


@dataclass
class BotEntry:
    spec: str          # "package.module:ClassName", as for terrabots-run --agent
    count: int = 1


@dataclass
class TeamEntry:
    """A team: its bots fight together. The first member is the team leader."""
    name: str
    members: list[BotEntry] = field(default_factory=list)


@dataclass
class BattleConfig:
    # --- Arena ---
    width: int = 48
    height: int = 48
    terrain: str = "procedural"          # "procedural" | "flat" | "map" (then `map` names it)
    map: str | None = None               # map name (./maps/ or built-in) or .json path;
                                         # a map sets the arena size itself
    seed: int | None = None              # same seed -> same terrain, spawns, results

    # --- Rounds ---
    rounds: int = 10
    max_ticks_per_round: int = 2000
    tick_delay_ms: int = 60              # viewer playback only (~16 ticks/s)

    # --- Bodies ---
    initial_energy: float = 100.0
    max_velocity: float = 8 / PX_PER_CELL           # Robocode 8 px/tick
    acceleration: float = 1 / PX_PER_CELL           # Robocode 1 px/tick²
    deceleration: float = 2 / PX_PER_CELL           # Robocode 2 px/tick²
    max_body_turn_deg: float = 10.0                 # at standstill
    body_turn_velocity_penalty: float = 0.75        # deg less per px/tick of speed
    max_gun_turn_deg: float = 20.0
    max_radar_turn_deg: float = 45.0
    body_half_width: float = 18 / PX_PER_CELL       # Robocode bots are 36x36 px squares

    # --- Gun ---
    min_bullet_power: float = 0.1
    max_bullet_power: float = 3.0
    bullet_speed_fixed: float | None = None  # cells/tick; None = Robocode 20 - 3p px/tick
    max_bullet_speed: float | None = None    # cap in cells/tick
    damage_formula: str = "robocode"         # 4p (+ 2(p-1) if p > 1) | damage_per_power * p
    damage_per_power: float = 4.0
    max_damage: float | None = None
    initial_gun_heat: float = 3.0            # Robocode: no shots in the first ~30 ticks
    gun_cooling_rate: float = 0.1
    hit_energy_return: str = "damage"        # "damage" | "robocode" (3p) | "none"

    # --- Radar ---
    radar_range: float = 1200 / PX_PER_CELL  # 75 cells, as in Robocode; line of sight
                                             # is what makes terrain matter
    radar_requires_los: bool = True

    # --- Collisions ---
    ram_damage: float = 0.6
    bullet_collisions: bool = True           # bullets that cross each other both vanish

    # --- Stalemates ---
    inactivity_time: int = 450               # ticks without damage before the drain starts
    inactivity_energy_drain: float = 0.1     # energy every bot loses per tick while inactive

    # --- Teams (Robocode: leader 200 energy, droid 120 and no radar) ---
    team_leader_bonus: float = 100.0         # extra start energy for a team's first member
    droid_bonus: float = 20.0                # extra start energy for droids (no radar)
    team_message_range: float | None = None  # None = teammates hear each other anywhere
                                             # (Robocode); a number = only within that many
                                             # cells and in line of sight, like shouting

    # --- Mode ---
    comms_enabled: bool = True
    decide_time_budget_ms: float | None = 20.0  # None/0 = unlimited (debugging)
    bot_storage_quota_kb: int = 200          # per bot class data folder (Robocode: 200 KB)
    bot_isolation: str = "none"              # "process": each bot in its own process
                                             # (hard time limit, parallel turns)

    def __post_init__(self) -> None:
        self.validate()

    # ------------------------------------------------------------------

    def validate(self) -> None:
        for name, choices in _CHOICES.items():
            value = getattr(self, name)
            if value not in choices:
                raise BattleConfigError(f"{name}: {value!r} is not one of {', '.join(choices)}")
        for name, (lo, hi) in _RANGES.items():
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value):
                raise BattleConfigError(f"{name}: expected a number, got {value!r}")
            if (lo is not None and value < lo) or (hi is not None and value > hi):
                raise BattleConfigError(f"{name}: {value} outside [{lo}, {hi if hi is not None else '∞'}]")
        if self.terrain == "map" and not self.map:
            raise BattleConfigError("map: choose a map when terrain is \"map\"")
        if self.map is not None and not isinstance(self.map, str):
            raise BattleConfigError(f"map: expected a map name, got {self.map!r}")
        if self.min_bullet_power > self.max_bullet_power:
            raise BattleConfigError("min_bullet_power: must not exceed max_bullet_power")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            raise BattleConfigError(f"seed: expected an integer or null, got {self.seed!r}")

    # ------------------------------------------------------------------
    # Derived rules
    # ------------------------------------------------------------------

    def bullet_speed(self, power: float) -> float:
        speed = (
            self.bullet_speed_fixed
            if self.bullet_speed_fixed is not None
            else (20.0 - 3.0 * power) / PX_PER_CELL
        )
        if self.max_bullet_speed is not None:
            speed = min(speed, self.max_bullet_speed)
        return speed

    def damage(self, power: float) -> float:
        if self.damage_formula == "robocode":
            dmg = 4.0 * power + (2.0 * (power - 1.0) if power > 1.0 else 0.0)
        else:
            dmg = self.damage_per_power * power
        if self.max_damage is not None:
            dmg = min(dmg, self.max_damage)
        return dmg

    def energy_return(self, power: float, damage_dealt: float) -> float:
        if self.hit_energy_return == "damage":
            return damage_dealt
        if self.hit_energy_return == "robocode":
            return 3.0 * power
        return 0.0

    def gun_heat(self, power: float) -> float:
        return 1.0 + power / 5.0

    def max_body_turn(self, velocity: float) -> float:
        """Robocode: 10 - 0.75·|v| degrees, with v in px/tick."""
        v_px = abs(velocity) * PX_PER_CELL
        return max(0.0, self.max_body_turn_deg - self.body_turn_velocity_penalty * v_px)

    def wall_damage(self, velocity: float) -> float:
        """Robocode: max(0, |v|/2 - 1), with v in px/tick."""
        return max(0.0, abs(velocity) * PX_PER_CELL * 0.5 - 1.0)

    # ------------------------------------------------------------------
    # (De)serialisation
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BattleConfig":
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise BattleConfigError(f"{unknown[0]}: unknown setting")
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class BattleFile:
    """A parsed battle TOML: settings plus the bots that fight."""
    config: BattleConfig
    bots: list[BotEntry] = field(default_factory=list)     # each fights for itself
    teams: list[TeamEntry] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BattleFile":
        data = dict(data)
        bots = _bot_entries(data.pop("bots", []), "bots")
        raw_teams = data.pop("teams", [])
        if not isinstance(raw_teams, list):
            raise BattleConfigError("teams: expected a list of [[teams]] tables")
        teams = []
        for i, t in enumerate(raw_teams):
            if not isinstance(t, dict):
                raise BattleConfigError(f"teams[{i}]: expected a table with name and members")
            teams.append(TeamEntry(str(t.get("name", "")), _bot_entries(t.get("members", []), f"teams[{i}].members")))
        validate_teams(teams)
        return cls(config=BattleConfig.from_dict(data), bots=bots, teams=teams)

    @classmethod
    def load(cls, path: str | Path) -> "BattleFile":
        with open(path, "rb") as f:
            return cls.from_dict(tomllib.load(f))

    def to_toml(self) -> str:
        """Hand-written TOML: the standard library can read TOML but not write it."""
        lines = []
        for key, value in self.config.to_dict().items():
            if value is None:
                lines.append(f"# {key} = (unset)")
            else:
                lines.append(f"{key} = {_toml_value(value)}")
        for b in self.bots:
            lines += ["", "[[bots]]", f"spec = {_toml_value(b.spec)}", f"count = {b.count}"]
        for t in self.teams:
            lines += ["", "[[teams]]", f"name = {_toml_value(t.name)}"]
            for b in t.members:
                lines += ["[[teams.members]]", f"spec = {_toml_value(b.spec)}", f"count = {b.count}"]
        return "\n".join(lines) + "\n"


def _bot_entries(raw: Any, where: str) -> list[BotEntry]:
    if not isinstance(raw, list):
        raise BattleConfigError(f"{where}: expected a list")
    out = []
    for i, b in enumerate(raw):
        if not isinstance(b, dict) or "spec" not in b:
            raise BattleConfigError(f"{where}[{i}]: needs a 'spec' like 'module:Class'")
        count = b.get("count", 1)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise BattleConfigError(f"{where}[{i}].count: expected a positive integer")
        out.append(BotEntry(spec=str(b["spec"]), count=count))
    return out


def validate_teams(teams: list[TeamEntry]) -> None:
    if len(teams) > MAX_TEAMS:
        raise BattleConfigError(f"teams: at most {MAX_TEAMS} teams")
    seen = set()
    for i, t in enumerate(teams):
        name = t.name.strip()
        if not name or len(name) > MAX_TEAM_NAME:
            raise BattleConfigError(f"teams[{i}].name: 1 to {MAX_TEAM_NAME} characters")
        if name in seen:
            raise BattleConfigError(f"teams[{i}].name: {name!r} is used twice")
        seen.add(name)
        if not t.members:
            raise BattleConfigError(f"teams[{i}] ({name}): needs at least one member")


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return repr(value)
