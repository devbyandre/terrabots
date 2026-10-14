package robocode;

/** A bullet you fired (or that hit you), as Robocode's robocode.Bullet. */
public class Bullet implements java.io.Serializable {
    private final double heading, x, y, power;
    private final String owner;
    String victim;
    boolean active;
    final long firedAt;

    Bullet(double heading, double x, double y, double power, String owner, String victim, boolean active, long firedAt) {
        this.heading = heading; this.x = x; this.y = y; this.power = power;
        this.owner = owner; this.victim = victim; this.active = active; this.firedAt = firedAt;
    }

    public double getHeading() { return heading; }
    public double getHeadingRadians() { return Math.toRadians(heading); }
    public String getName() { return owner; }
    public double getPower() { return power; }
    public double getVelocity() { return Rules.getBulletSpeed(power); }
    public String getVictim() { return victim; }
    public double getX() { return x; }
    public double getY() { return y; }
    public boolean isActive() { return active; }
}
