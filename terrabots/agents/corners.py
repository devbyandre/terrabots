"""Corners: drives into a corner and defends it, sweeping its gun, like
Robocode's sample. It remembers in its persistent storage how often it died in
each corner, across battles, and picks the corner where it survived best."""

import math

from terrabots.battle import BattleAction, BattleAgent, BattleObservation
from terrabots.battle.geometry import distance, heading_to, normalize_angle

INSET = 2.5          # cells from the edges


class Corners(BattleAgent):
    """Camps in its best corner (learned across battles) and sweeps its gun."""

    adjust_gun_for_body_turn = True

    def on_round_start(self, round_number, rounds):
        self.stats = self.storage.load("corners", default={"deaths": [0, 0, 0, 0], "rounds": [0, 0, 0, 0]})
        # Lowest death rate, trying unplayed corners first.
        rates = [d / r if r else -1 for d, r in zip(self.stats["deaths"], self.stats["rounds"])]
        self.corner = min(range(4), key=lambda i: rates[i])
        self.sweep = 1
        self.blocked = 0

    def decide(self, obs: BattleObservation) -> BattleAction:
        w, h = obs.arena_width, obs.arena_height
        cx, cy = [(INSET, INSET), (INSET, h - INSET), (w - INSET, h - INSET), (w - INSET, INSET)][self.corner]
        centre_bearing = heading_to(cx, cy, w / 2, h / 2)
        if obs.hit_wall:
            self.blocked += 1
            if self.blocked > 20:                 # unreachable (terrain): next corner
                self.corner, self.blocked = (self.corner + 1) % 4, 0
        action = BattleAction()
        if distance(obs.x, obs.y, cx, cy) > 0.8:
            course = heading_to(obs.x, obs.y, cx, cy)
            turn = normalize_angle(course - obs.heading)
            if abs(turn) > 90:                    # reversing is the shorter turn
                turn = normalize_angle(turn + 180)
                speed = -0.5
            else:
                speed = 0.5
            action = BattleAction(velocity=speed if abs(turn) < 30 else 0.0, body_turn=turn)
        # Sweep the gun across the 90° the corner faces; the radar rides on it.
        offset = normalize_angle(obs.gun_heading - centre_bearing)
        if abs(offset) > 45:
            self.sweep = -1 if offset > 0 else 1
        action.gun_turn = 6 * self.sweep
        if obs.scanned_bots:
            near = min(obs.scanned_bots, key=lambda s: s.distance)
            action.gun_turn = normalize_angle(near.bearing - obs.gun_heading)
            if obs.gun_heat == 0 and abs(action.gun_turn) < 5:
                action.fire = 3.0 if near.distance < 12 else 1.5
        return action

    def on_round_end(self, won):
        self.stats["rounds"][self.corner] += 1
        self.storage.save("corners", self.stats)

    def on_death(self):
        self.stats["deaths"][self.corner] += 1
