"""SpinBot: drives in circles with its gun spinning, fires at whatever the radar sweeps.

The radar rides on the gun (Robocode default), so whenever the radar sweeps a bot
the gun is already pointing roughly at it. No aiming math at all.
"""

from terrabots.battle import BattleAction, BattleAgent, BattleObservation


class SpinBot(BattleAgent):
    """Circles and spins its gun; fires at anything the radar sweeps."""

    def decide(self, obs: BattleObservation) -> BattleAction:
        fire = 0.0
        if obs.scanned_bots:
            nearest = min(obs.scanned_bots, key=lambda s: s.distance)
            fire = 3.0 if nearest.distance < 8 else 1.5
        # Reverse when we hit a wall, so we don't grind along it.
        direction = -1.0 if obs.hit_wall and obs.velocity >= 0 else 1.0
        return BattleAction(velocity=direction * 0.5, body_turn=10, gun_turn=20, fire=fire)
