"""
Squad: a demo team. The leader's radar spins and it tells the team where every
enemy is; the droids have no radar at all and aim with what the leader tells
them. Everyone shares their position, so nobody fires through a teammate.

Run it (battles/teams.toml):

    terrabots-battle battles/teams.toml

What it shows: team messages (broadcast, obs.team_messages), droids, and that
friendly fire is real, so a team needs to check its line of fire.
"""

from __future__ import annotations

import math
import random

from terrabots.battle import BattleAction, BattleAgent, BattleObservation
from terrabots.battle.geometry import distance, heading_to, normalize_angle, project

POWER = 2.0
STALE = 12          # ticks after which an enemy report is too old to aim at
SAFE_LINE = 1.6     # cells: don't fire if a teammate is this close to the line of fire


class _SquadBot(BattleAgent):
    adjust_gun_for_body_turn = True
    adjust_radar_for_gun_turn = True

    def on_round_start(self, round_number: int, rounds: int) -> None:
        self.enemies: dict[int, dict] = {}       # id -> last known x, y, heading, velocity, tick
        self.friends: dict[int, tuple[float, float]] = {}
        self.direction = 1
        self.colors = {"body": "#3d6fb6", "gun": "#9fc3f0", "radar": "#f2b33d"}

    def decide(self, obs: BattleObservation) -> BattleAction:
        self.read_messages(obs)
        for s in obs.scanned_bots:
            if not s.teammate:
                x, y = project(obs.x, obs.y, s.bearing, s.distance)
                self.enemies[s.bot_id] = {"x": x, "y": y, "h": s.heading, "v": s.velocity, "t": obs.tick}
        for d in obs.bot_death:
            self.enemies.pop(d.bot_id, None)
            self.friends.pop(d.bot_id, None)
        self.broadcast({"me": [obs.x, obs.y],
                        "enemies": {i: e for i, e in self.enemies.items() if e["t"] == obs.tick}})

        target = self.pick_target(obs)
        action = BattleAction(velocity=0.5 * self.direction, radar_turn=45)
        if random.random() < 0.03:
            self.direction = -self.direction
        if target is None:
            action.body_turn = 5
            return action
        tx, ty = self.lead(obs, target)
        aim = normalize_angle(heading_to(obs.x, obs.y, tx, ty) - obs.gun_heading)
        action.gun_turn = aim
        # Drive across the target's line of fire, curving back towards the middle near walls.
        action.body_turn = normalize_angle(heading_to(obs.x, obs.y, target["x"], target["y"]) + 90 - obs.heading)
        margin = 5
        if not (margin < obs.x < obs.arena_width - margin and margin < obs.y < obs.arena_height - margin):
            action.body_turn = normalize_angle(heading_to(obs.x, obs.y, obs.arena_width / 2, obs.arena_height / 2)
                                               - obs.heading)
            action.velocity = 0.5
        if abs(aim) < 3 and obs.gun_heat == 0 and self.line_clear(obs, tx, ty):
            action.fire = POWER
        return action

    def read_messages(self, obs: BattleObservation) -> None:
        for m in obs.team_messages:
            self.friends[m.sender_id] = tuple(m.data["me"])
            for i, e in m.data["enemies"].items():
                i = int(i)     # JSON object keys are strings
                if i not in self.enemies or self.enemies[i]["t"] < e["t"]:
                    self.enemies[i] = e

    def pick_target(self, obs: BattleObservation) -> dict | None:
        fresh = [e for e in self.enemies.values() if obs.tick - e["t"] <= STALE]
        return min(fresh, key=lambda e: distance(obs.x, obs.y, e["x"], e["y"]), default=None)

    def lead(self, obs: BattleObservation, e: dict) -> tuple[float, float]:
        """Linear targeting from the last report, counting the ticks since it was made."""
        speed = self.rules.bullet_speed(POWER)
        x, y = project(e["x"], e["y"], e["h"], e["v"] * (obs.tick - e["t"]))
        px, py = x, y
        for _ in range(8):
            ticks = distance(obs.x, obs.y, px, py) / speed
            px, py = project(x, y, e["h"], e["v"] * ticks)
        return (min(max(px, 1), obs.arena_width - 1), min(max(py, 1), obs.arena_height - 1))

    def line_clear(self, obs: BattleObservation, tx: float, ty: float) -> bool:
        """No teammate near the segment from us to the aim point."""
        length = distance(obs.x, obs.y, tx, ty)
        if length == 0:
            return True
        ux, uy = (tx - obs.x) / length, (ty - obs.y) / length
        for fx, fy in self.friends.values():
            along = (fx - obs.x) * ux + (fy - obs.y) * uy
            if 0 < along < length and abs((fx - obs.x) * uy - (fy - obs.y) * ux) < SAFE_LINE:
                return False
        return True


class SquadLeader(_SquadBot):
    """Squad leader: spins its radar and reports every enemy to the team."""


class SquadDroid(_SquadBot):
    """Squad droid: no radar, aims at what the leader reports."""

    droid = True
