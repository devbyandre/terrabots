package robocode;

/** Robocode's BattleEndedEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class BattleEndedEvent extends Event {
    private final boolean aborted;
    private final BattleResults results;

    public BattleEndedEvent(boolean aborted, BattleResults results) {
        this.aborted = aborted;
        this.results = results;
    }

    public boolean isAborted() { return aborted; }
    public BattleResults getResults() { return results; }

    @Override
    int defaultPriority() { return 100; }

    @Override
    void dispatch(Robot r) { r.onBattleEnded(this); }
}
