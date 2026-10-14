package robocode.robotinterfaces;

public interface IAdvancedEvents {
    void onSkippedTurn(robocode.SkippedTurnEvent event);
    void onCustomEvent(robocode.CustomEvent event);
}
