"""
FirstTank — the smallest battle bot, and the template for writing your own.

Copy this file to bots/my_tank.py, rename the class, and fight the demo bots:

    terrabots-battle --headless --bot bots.my_tank:MyTank --bot terrabots.agents.tracker:Tracker

Or run `terrabots-battle` and pick it in the setup screen: bots in bots/ are listed
automatically. In VS Code, breakpoints inside decide() work (turn time limits are
switched off under the debugger).
"""

from terrabots.battle import BattleAction, BattleAgent, BattleObservation
from terrabots.battle.geometry import normalize_angle


class FirstTank(BattleAgent):
    """Sweeps its gun until the radar sees someone, then aims and fires."""

    # The radar sits on the gun and turns with it (Robocode default), so wherever
    # the radar sees an enemy, the gun is close to pointing at it.

    def decide(self, obs: BattleObservation) -> BattleAction:
        if not obs.scanned_bots:
            return BattleAction(velocity=0.3, body_turn=4, gun_turn=20)   # search

        enemy = obs.scanned_bots[0]
        aim = normalize_angle(enemy.bearing - obs.gun_heading)   # how far to turn the gun
        fire = 2.0 if abs(aim) < 5 and obs.gun_heat == 0 else 0.0
        if fire:
            self.log(f"firing at {enemy.name}, {enemy.distance:.1f} cells away")   # shows in the console (C)
        return BattleAction(velocity=0.3, body_turn=4, gun_turn=aim, fire=fire)
