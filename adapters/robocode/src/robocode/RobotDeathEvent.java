package robocode;

/** Robocode's RobotDeathEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class RobotDeathEvent extends Event {
    private final String name;

    public RobotDeathEvent(String name) {
        this.name = name;
    }

    public String getName() { return name; }

    @Override
    int defaultPriority() { return 70; }

    @Override
    void dispatch(Robot r) { r.onRobotDeath(this); }
}
