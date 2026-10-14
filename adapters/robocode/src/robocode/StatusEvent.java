package robocode;

/** Robocode's StatusEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class StatusEvent extends Event {
    private final RobotStatus status;

    public StatusEvent(RobotStatus status) {
        this.status = status;
    }

    public RobotStatus getStatus() { return status; }

    @Override
    int defaultPriority() { return 99; }

    @Override
    void dispatch(_Peer p) { if (p.basic != null) p.basic.onStatus(this); }
}
