"""SittingDuck: never moves, never fires. A target for testing aim."""

from terrabots.battle import BattleAction, BattleAgent, BattleObservation


class SittingDuck(BattleAgent):
    """Stands still and does nothing."""

    def decide(self, obs: BattleObservation) -> BattleAction:
        return BattleAction()
