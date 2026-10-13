"""Learner: a compact GuessFactor gun plus orbiting movement with random
reversals. It saves what its gun learned per opponent in persistent storage,
so it aims better the more battles it has fought against someone.

How the gun works, in short: every tick it sends an imaginary wave at the
target. When the wave reaches the target, it records where the target ended
up as a "guess factor" between -1 and +1 (how far it got along its sideways
direction, relative to the farthest it could have got). To aim, it picks the
most visited guess factor.
"""

import math
import random

from terrabots.battle import BattleAction, BattleAgent, BattleObservation
from terrabots.battle.geometry import distance, heading_to, normalize_angle, project

BINS = 31
POWER = 2.0


class Learner(BattleAgent):
    """Orbits and dodges; aims with a guess-factor gun that learns across battles."""

    adjust_gun_for_body_turn = True
    adjust_radar_for_gun_turn = True

    def on_round_start(self, round_number, rounds):
        self.waves = []
        self.direction = 1
        self.stats = self.storage.load("guess_factors", default={})

    def decide(self, obs: BattleObservation) -> BattleAction:
        action = BattleAction(radar_turn=45)
        if not obs.scanned_bots:
            action.velocity, action.body_turn = 0.3, 4
            return action
        t = min(obs.scanned_bots, key=lambda s: s.distance)
        tx, ty = project(obs.x, obs.y, t.bearing, t.distance)
        bins = self.stats.setdefault(t.class_name, [0] * BINS)
        speed = self.rules.bullet_speed(POWER)
        max_escape = math.degrees(math.asin(min(1.0, self.rules.max_velocity / speed)))
        lateral = 1 if t.velocity * math.sin(math.radians(t.heading - t.bearing)) >= 0 else -1

        # Resolve waves that reached the target; send a new one.
        for w in list(self.waves):
            if speed * (obs.tick - w["tick"]) >= distance(w["x"], w["y"], tx, ty):
                offset = normalize_angle(heading_to(w["x"], w["y"], tx, ty) - w["bearing"])
                gf = max(-1.0, min(1.0, offset / max_escape * w["lateral"]))
                bins[round((gf + 1) / 2 * (BINS - 1))] += 1
                self.waves.remove(w)
        self.waves.append({"x": obs.x, "y": obs.y, "tick": obs.tick, "bearing": t.bearing, "lateral": lateral})

        best = max(range(BINS), key=lambda i: bins[i])
        aim = t.bearing + ((best / (BINS - 1)) * 2 - 1) * max_escape * lateral
        action.gun_turn = normalize_angle(aim - obs.gun_heading)
        action.radar_turn = normalize_angle(t.bearing - obs.radar_heading) * 2 or 10
        if obs.gun_heat == 0 and abs(action.gun_turn) < 4:
            action.fire = POWER

        # Orbit at right angles to the target; reverse at random and at walls.
        if random.random() < 0.05 or obs.hit_wall:
            self.direction *= -1
        nx, ny = project(obs.x, obs.y, obs.heading, 3 * self.direction)
        if not (2 < nx < obs.arena_width - 2 and 2 < ny < obs.arena_height - 2):
            self.direction *= -1
        drift = 15 if t.distance > 14 else -15        # keep roughly 14 cells away
        action.body_turn = normalize_angle(t.bearing + 90 - drift * self.direction - obs.heading)
        if abs(action.body_turn) > 90:
            action.body_turn = normalize_angle(action.body_turn + 180)
        action.velocity = 0.5 * self.direction
        return action

    def on_round_end(self, won):
        self.storage.save("guess_factors", self.stats)
