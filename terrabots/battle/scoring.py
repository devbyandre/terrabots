"""
Robocode scoring (RoboWiki: Robocode/Scoring), per round and summed per battle.

| Component         | Points                                                   |
|-------------------|----------------------------------------------------------|
| Survival          | 50 every time another bot dies while you are alive       |
| Last survivor     | 10 for each bot that died before you                     |
| Bullet damage     | 1 per point of damage dealt                              |
| Bullet kill bonus | 20 % of all the damage you did to a bot you killed       |
| Ram damage        | 2 per point of damage dealt by ramming                   |
| Ram kill bonus    | 30 % of all the damage you did to a bot you rammed dead  |

"All the damage" is read literally (bullet + ram damage to that bot). 1sts, 2nds
and 3rds don't add points; they show how often a bot placed.

Teams: every bot belongs to a team; a bot fighting alone is a team of one, which
gives exactly the rules above. With real teams:
- Damage to a teammate scores nothing and earns no kill bonus (friendly fire
  still hurts).
- Survival points go to standing bots when a bot of *another* team dies.
- The last-survivor bonus goes to each standing member of the last team, 10 per
  enemy bot.
- Places are team places: every member of the winning team gets a 1st.
A team's score is the sum of its members' scores.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Hashable

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
    teams: dict[int, Hashable] = field(default_factory=dict)   # bot id -> team; missing = alone
    # all damage dealt, by (attacker, victim), for kill bonuses
    _dealt: dict[tuple[int, int], float] = field(default_factory=lambda: defaultdict(float))
    death_order: list[int] = field(default_factory=list)
    team_ranking: list[Hashable] = field(default_factory=list)   # set by finish(), 1st first

    def team_of(self, bot_id: int) -> Hashable:
        return self.teams.get(bot_id, ("solo", bot_id))

    def friends(self, a: int, b: int) -> bool:
        return a != b and self.team_of(a) == self.team_of(b)

    def shot(self, shooter: int) -> None:
        self.scores[shooter].shots += 1

    def bullet_hit(self, shooter: int, victim: int, dealt: float) -> None:
        if self.friends(shooter, victim):
            return
        s = self.scores[shooter]
        s.hits += 1
        s.bullet_damage += dealt
        self._dealt[(shooter, victim)] += dealt

    def ram(self, rammer: int, victim: int, dealt: float) -> None:
        if self.friends(rammer, victim):
            return
        self.scores[rammer].ram_damage += dealt
        self._dealt[(rammer, victim)] += dealt

    def death(self, victim: int, killer: int | None, killed_by_ram: bool,
              survivors: list[int]) -> None:
        self.death_order.append(victim)
        for bot_id in survivors:
            if self.team_of(bot_id) != self.team_of(victim):
                self.scores[bot_id].survival += SURVIVAL_PER_DEATH
        if killer is not None and killer != victim and not self.friends(killer, victim):
            dealt = self._dealt[(killer, victim)]
            if killed_by_ram:
                self.scores[killer].ram_kill_bonus += RAM_KILL_BONUS * dealt
            else:
                self.scores[killer].bullet_kill_bonus += BULLET_KILL_BONUS * dealt

    def finish(self, survivors_by_energy: list[tuple[int, float]], n_bots: int) -> list[int]:
        """Award last-survivor bonus and placements. Returns bot ids, 1st place first
        (members of a better-placed team before those of a worse one)."""
        standing: dict[Hashable, list[tuple[int, float]]] = {}
        for bid, energy in survivors_by_energy:
            standing.setdefault(self.team_of(bid), []).append((bid, energy))
        if len(standing) == 1:
            (team, members), = standing.items()
            enemies = sum(1 for bid in self.scores if self.team_of(bid) != team)
            for bid, _ in members:
                self.scores[bid].last_survivor += LAST_SURVIVOR_PER_ENEMY * enemies
        # Standing teams by total energy, then teams in reverse order of elimination
        # (a team is out when its last member dies).
        order = sorted(standing, key=lambda t: -sum(e for _, e in standing[t]))
        for bid in reversed(self.death_order):
            team = self.team_of(bid)
            if team not in order:
                order.append(team)
        self.team_ranking = order
        alive = [bid for bid, _ in survivors_by_energy]
        dead_last_first = list(reversed(self.death_order))
        ranking = [bid for team in order for bid in alive + dead_last_first if self.team_of(bid) == team]
        for place, team in enumerate(order[:3]):
            for bid in ranking:
                if self.team_of(bid) != team:
                    continue
                s = self.scores[bid]
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
