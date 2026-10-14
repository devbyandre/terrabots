package robocode;

/** Robocode's ScannedRobotEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class ScannedRobotEvent extends Event {
    private final String name;
    private final double energy;
    private final double bearing;
    private final double distance;
    private final double heading;
    private final double velocity;
    private final boolean isSentryRobot;

    public ScannedRobotEvent(String name, double energy, double bearing, double distance, double heading, double velocity, boolean isSentryRobot) {
        this.name = name;
        this.energy = energy;
        this.bearing = bearing;
        this.distance = distance;
        this.heading = heading;
        this.velocity = velocity;
        this.isSentryRobot = isSentryRobot;
    }

    public String getName() { return name; }
    public double getEnergy() { return energy; }
    public double getBearing() { return bearing; }
    public double getBearingRadians() { return Math.toRadians(bearing); }
    public double getDistance() { return distance; }
    public double getHeading() { return heading; }
    public double getHeadingRadians() { return Math.toRadians(heading); }
    public double getVelocity() { return velocity; }
    public boolean isSentryRobot() { return isSentryRobot; }
    @Deprecated public String getRobotName() { return name; }
    @Deprecated public double getLife() { return energy; }
    @Deprecated public double getRobotBearing() { return bearing; }
    @Deprecated public double getRobotDistance() { return distance; }
    @Deprecated public double getRobotHeading() { return heading; }
    @Deprecated public double getRobotVelocity() { return velocity; }

    @Override
    int defaultPriority() { return 10; }

    @Override
    void dispatch(Robot r) { r.onScannedRobot(this); }
}
