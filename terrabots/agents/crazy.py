"""Crazy: erratic movement plus linear targeting (aims where the enemy will be if it
keeps its heading and speed). A harder target than SpinBot and a better shot.
"""

import random

from terrabots.battle import BattleAction, BattleAgent, BattleObservation
from terrabots.battle.geometry import heading_to, normalize_angle, project


class Crazy(BattleAgent):
    """Random zig-zags; linear-prediction gun."""

    adjust_gun_for_body_turn = True
    adjust_radar_for_gun_turn = True

    def on_round_start(self, round_number: int, rounds: int) -> None:
        self.turn = 0.0
        self.velocity = 0.5
        self.ticks_left = 0
        self.radar_dir = 1.0

    def decide(self, obs: BattleObservation) -> BattleAction:
        self.ticks_left -= 1
        if self.ticks_left <= 0 or obs.hit_wall or obs.hit_bot:
            self.turn = random.uniform(-10, 10)
            self.velocity = random.choice([-0.5, 0.5]) if not obs.hit_wall else -self.velocity
            self.ticks_left = random.randint(10, 40)

        action = BattleAction(velocity=self.velocity, body_turn=self.turn,
                              radar_turn=45 * self.radar_dir)
        if not obs.scanned_bots:
            return action

        target = min(obs.scanned_bots, key=lambda s: s.distance)
        tx, ty = project(obs.x, obs.y, target.bearing, target.distance)
        power = 2.0
        bullet_speed = (20 - 3 * power) / 16  # default arena rule; see BattleConfig.bullet_speed
        # Iterate: where is the target when a bullet fired now could reach it?
        px, py = tx, ty
        for _ in range(10):
            ticks = ((px - obs.x) ** 2 + (py - obs.y) ** 2) ** 0.5 / bullet_speed
            px, py = project(tx, ty, target.heading, target.velocity * ticks)
            px = min(max(px, 0.5), obs.arena_width - 0.5)
            py = min(max(py, 0.5), obs.arena_height - 0.5)
        aim = heading_to(obs.x, obs.y, px, py)

        radar_err = normalize_angle(target.bearing - obs.radar_heading)
        self.radar_dir = 1.0 if radar_err >= 0 else -1.0
        action.radar_turn = radar_err * 2
        action.gun_turn = normalize_angle(aim - obs.gun_heading)
        if obs.gun_heat == 0 and abs(action.gun_turn) < 5:
            action.fire = power
        return action
