"""Tracker: locks its radar on one enemy, aims straight at it (head-on targeting),
and keeps a medium distance.

Shows the three independent headings: with both adjust flags set, body, gun and
radar each turn only by their own command.
"""

from terrabots.battle import BattleAction, BattleAgent, BattleObservation
from terrabots.battle.geometry import normalize_angle

PREFERRED_DISTANCE = 10.0


class Tracker(BattleAgent):
    """Radar lock, head-on aim, keeps ~10 cells distance."""

    adjust_gun_for_body_turn = True
    adjust_radar_for_gun_turn = True

    def on_round_start(self, round_number: int, rounds: int) -> None:
        self.target_id: int | None = None

    def decide(self, obs: BattleObservation) -> BattleAction:
        scans = obs.scanned_bots
        if self.target_id is not None:
            scans = [s for s in scans if s.bot_id == self.target_id] or scans
        if not scans:
            self.target_id = None
            return BattleAction(velocity=0.2, body_turn=5, radar_turn=45)  # search

        target = min(scans, key=lambda s: s.distance)
        self.target_id = target.bot_id

        # Radar: turn past the target so next tick's sweep crosses it again (lock).
        radar_err = normalize_angle(target.bearing - obs.radar_heading)
        radar_turn = radar_err * 2 if radar_err else 10
        gun_err = normalize_angle(target.bearing - obs.gun_heading)

        # Drive perpendicular to the target, drifting in or out to hold distance.
        drift = 20 if target.distance > PREFERRED_DISTANCE else -20
        body_err = normalize_angle(target.bearing + 90 - drift - obs.heading)
        velocity = 0.5 if abs(body_err) < 90 else -0.5
        if abs(body_err) >= 90:
            body_err = normalize_angle(body_err + 180)
        if obs.hit_wall:
            velocity = -velocity

        fire = 0.0
        if obs.gun_heat == 0 and abs(gun_err) < 4:
            fire = 3.0 if target.distance < 6 else 2.0 if target.distance < 15 else 1.0
        return BattleAction(velocity=velocity, body_turn=body_err, gun_turn=gun_err,
                            radar_turn=radar_turn, fire=fire)
