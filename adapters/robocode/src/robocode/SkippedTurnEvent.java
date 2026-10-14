package robocode;

/** Robocode's SkippedTurnEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class SkippedTurnEvent extends Event {
    private final long skippedTurn;

    public SkippedTurnEvent(long skippedTurn) {
        this.skippedTurn = skippedTurn;
    }

    public long getSkippedTurn() { return skippedTurn; }

    @Override
    int defaultPriority() { return 100; }

    @Override
    void dispatch(Robot r) { if (r instanceof AdvancedRobot) ((AdvancedRobot) r).onSkippedTurn(this); }
}
