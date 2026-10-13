"""RamFire: drives straight at the nearest enemy and rams it, like Robocode's
sample. Ramming scores 2 points per point of damage (bullets score 1), so it
fires only weak shots up close that won't take the ram kill away."""

from terrabots.battle import BattleAction, BattleAgent, BattleObservation
from terrabots.battle.geometry import normalize_angle


class RamFire(BattleAgent):
    """Charges the nearest enemy and rams it; weak shots point-blank."""

    adjust_gun_for_body_turn = True
    adjust_radar_for_gun_turn = True

    def on_round_start(self, round_number, rounds):
        self.target = None

    def decide(self, obs: BattleObservation) -> BattleAction:
        if obs.scanned_bots:
            self.target = min(obs.scanned_bots, key=lambda s: s.distance)
        if self.target is None or not obs.scanned_bots:
            return BattleAction(velocity=0.2, body_turn=5, radar_turn=45)
        t = self.target
        body = normalize_angle(t.bearing - obs.heading)
        gun = normalize_angle(t.bearing - obs.gun_heading)
        radar = normalize_angle(t.bearing - obs.radar_heading) * 2 or 10
        fire = 0.0
        if obs.gun_heat == 0 and abs(gun) < 8 and t.distance < 5:
            fire = 0.5 if t.energy > 3 else 0.1      # leave the kill to the ram
        return BattleAction(velocity=0.5 if abs(body) < 60 else 0.1, body_turn=body,
                            gun_turn=gun, radar_turn=radar, fire=fire)
