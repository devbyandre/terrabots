package robocode;

/** Robocode's HitByBulletEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class HitByBulletEvent extends Event {
    private final double bearing;
    private final Bullet bullet;

    public HitByBulletEvent(double bearing, Bullet bullet) {
        this.bearing = bearing;
        this.bullet = bullet;
    }

    public double getBearing() { return bearing; }
    public double getBearingRadians() { return Math.toRadians(bearing); }
    public Bullet getBullet() { return bullet; }
    public double getHeading() { return bullet.getHeading(); }
    public double getHeadingRadians() { return bullet.getHeadingRadians(); }
    public String getName() { return bullet.getName(); }
    public double getPower() { return bullet.getPower(); }
    public double getVelocity() { return bullet.getVelocity(); }

    @Override
    int defaultPriority() { return 20; }

    @Override
    void dispatch(Robot r) { r.onHitByBullet(this); }
}
