package robocode;

/** Robocode's HitRobotEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class HitRobotEvent extends Event {
    private final String name;
    private final double bearing;
    private final double energy;
    private final boolean atFault;

    public HitRobotEvent(String name, double bearing, double energy, boolean atFault) {
        this.name = name;
        this.bearing = bearing;
        this.energy = energy;
        this.atFault = atFault;
    }

    public String getName() { return name; }
    public double getBearing() { return bearing; }
    public double getBearingRadians() { return Math.toRadians(bearing); }
    public double getEnergy() { return energy; }
    public boolean isMyFault() { return atFault; }

    @Override
    int defaultPriority() { return 40; }

    @Override
    void dispatch(_Peer p) { if (p.basic != null) p.basic.onHitRobot(this); }
}
