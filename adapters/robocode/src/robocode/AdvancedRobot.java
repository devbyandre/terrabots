package robocode;

import robocode.robotinterfaces.IAdvancedEvents;
import robocode.robotinterfaces.IAdvancedRobot;

/** Robocode's AdvancedRobot: queued commands (setAhead...) that run on execute(). */
public class AdvancedRobot extends _AdvancedRadiansRobot implements IAdvancedEvents, IAdvancedRobot {
    @Override public final IAdvancedEvents getAdvancedEventListener() { return this; }
    @Override public void onCustomEvent(CustomEvent e) { }
    @Override public void onSkippedTurn(SkippedTurnEvent e) { }
}
