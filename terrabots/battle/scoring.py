"""
Robocode-like scoring (docs/arena-spec.md §7), per round and summed per battle.

| Component         | Points                                         |
|-------------------|------------------------------------------------|
| Survival          | 50 per enemy that dies while you are alive     |
| Last survivor     | 10 × enemies at round start                    |
| Bullet damage     | 1 per point of damage dealt                    |
| Bullet kill bonus | 20 % of bullet damage dealt to a bot you killed|
| Ram damage        | 2 per point                                    |
| Ram kill bonus    | 30 % of ram damage dealt to a bot you killed   |
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass, field

SURVIVAL_PER_DEATH = 50.0
LAST_SURVIVOR_PER_ENEMY = 10.0
BULLET_DAMAGE_POINTS = 1.0
BULLET_KILL_BONUS = 0.20
RAM_DAMAGE_POINTS = 2.0
RAM_KILL_BONUS = 0.30


@dataclass
class BotScore:
    """One bot's points and counters, for one round or summed over a battle."""
    name: str
    class_name: str
    survival: float = 0.0
    last_survivor: float = 0.0
    bullet_damage: float = 0.0
    bullet_kill_bonus: float = 0.0
    ram_damage: float = 0.0
    ram_kill_bonus: float = 0.0
    firsts: int = 0
    seconds: int = 0
    thirds: int = 0
    shots: int = 0
    hits: int = 0
    end_energy_sum: float = 0.0   # energy at round end (0 if destroyed), summed
    rounds: int = 0
    skipped_turns: int = 0

    @property
    def total(self) -> float:
        return (self.survival + self.last_survivor
                + self.bullet_damage * BULLET_DAMAGE_POINTS + self.bullet_kill_bonus
                + self.ram_damage * RAM_DAMAGE_POINTS + self.ram_kill_bonus)

    @property
    def hit_rate(self) -> float:
        return self.hits / self.shots if self.shots else 0.0

    def add(self, other: "BotScore") -> None:
        for f in dataclasses.fields(self):
            if f.name not in ("name", "class_name"):
                setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))

    def to_dict(self) -> dict[str, float | int | str]:
        d = dataclasses.asdict(self)
        d["total"] = round(self.total, 2)
        d["hit_rate"] = round(self.hit_rate, 4)
        d["avg_end_energy"] = round(self.end_energy_sum / self.rounds, 2) if self.rounds else 0.0
        return {k: round(v, 2) if isinstance(v, float) else v for k, v in d.items()}


@dataclass
class RoundScorer:
    """Accumulates scoring events during one round."""
    scores: dict[int, BotScore]
    # bullet / ram damage dealt, by (attacker, victim), for kill bonuses
    _bullet_dealt: dict[tuple[int, int], float] = field(default_factory=lambda: defaultdict(float))
    _ram_dealt: dict[tuple[int, int], float] = field(default_factory=lambda: defaultdict(float))
    death_order: list[int] = field(default_factory=list)

    def shot(self, shooter: int) -> None:
        self.scores[shooter].shots += 1

    def bullet_hit(self, shooter: int, victim: int, dealt: float) -> None:
        s = self.scores[shooter]
        s.hits += 1
        s.bullet_damage += dealt
        self._bullet_dealt[(shooter, victim)] += dealt

    def ram(self, rammer: int, victim: int, dealt: float) -> None:
        self.scores[rammer].ram_damage += dealt
        self._ram_dealt[(rammer, victim)] += dealt

    def death(self, victim: int, killer: int | None, killed_by_ram: bool,
              survivors: list[int]) -> None:
        self.death_order.append(victim)
        for bot_id in survivors:
            self.scores[bot_id].survival += SURVIVAL_PER_DEATH
        if killer is not None and killer != victim:
            if killed_by_ram:
                self.scores[killer].ram_kill_bonus += RAM_KILL_BONUS * self._ram_dealt[(killer, victim)] * RAM_DAMAGE_POINTS
            else:
                self.scores[killer].bullet_kill_bonus += BULLET_KILL_BONUS * self._bullet_dealt[(killer, victim)]

    def finish(self, survivors_by_energy: list[tuple[int, float]], n_bots: int) -> list[int]:
        """Award last-survivor bonus and placements. Returns bot ids, 1st place first."""
        if len(survivors_by_energy) == 1:
            winner = survivors_by_energy[0][0]
            self.scores[winner].last_survivor += LAST_SURVIVOR_PER_ENEMY * (n_bots - 1)
        ranking = [bid for bid, _ in survivors_by_energy] + list(reversed(self.death_order))
        for place, bot_id in enumerate(ranking[:3]):
            s = self.scores[bot_id]
            if place == 0:
                s.firsts += 1
            elif place == 1:
                s.seconds += 1
            else:
                s.thirds += 1
        for bot_id, energy in survivors_by_energy:
            self.scores[bot_id].end_energy_sum += energy
        for s in self.scores.values():
            s.rounds += 1
        return ranking
