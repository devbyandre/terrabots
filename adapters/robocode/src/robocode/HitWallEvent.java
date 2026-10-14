package robocode;

/** Robocode's HitWallEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class HitWallEvent extends Event {
    private final double bearing;

    public HitWallEvent(double bearing) {
        this.bearing = bearing;
    }

    public double getBearing() { return bearing; }
    public double getBearingRadians() { return Math.toRadians(bearing); }

    @Override
    int defaultPriority() { return 30; }

    @Override
    void dispatch(Robot r) { r.onHitWall(this); }
}
