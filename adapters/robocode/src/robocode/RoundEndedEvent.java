package robocode;

/** Robocode's RoundEndedEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class RoundEndedEvent extends Event {
    private final int round;
    private final int turns;
    private final int totalTurns;

    public RoundEndedEvent(int round, int turns, int totalTurns) {
        this.round = round;
        this.turns = turns;
        this.totalTurns = totalTurns;
    }

    public int getRound() { return round; }
    public int getTurns() { return turns; }
    public int getTotalTurns() { return totalTurns; }

    @Override
    int defaultPriority() { return 110; }

    @Override
    void dispatch(_Peer p) { if (p.basic instanceof robocode.robotinterfaces.IBasicEvents3) ((robocode.robotinterfaces.IBasicEvents3) p.basic).onRoundEnded(this); }
}
