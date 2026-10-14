package robocode;

import robocode.robotinterfaces.IAdvancedEvents;

/** Robocode's AdvancedRobot: queued commands (setAhead...) that run on execute(). */
public class AdvancedRobot extends _AdvancedRadiansRobot implements IAdvancedEvents {
    @Override public void onCustomEvent(CustomEvent e) { }
    @Override public void onSkippedTurn(SkippedTurnEvent e) { }
}
