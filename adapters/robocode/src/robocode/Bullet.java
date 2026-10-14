package robocode;

/** A bullet you fired (or that hit you), as Robocode's robocode.Bullet. */
public class Bullet implements java.io.Serializable {
    private final double heading, power;
    double x, y;           // where it is: firing point, then where it hit or ended
    private final String owner;
    String victim;
    boolean active;
    final long firedAt;

    /** Robocode's public constructor (some bots build Bullet objects for their own bookkeeping). */
    public Bullet(double heading, double x, double y, double power, String ownerName, String victimName,
                  boolean isActive, int bulletId) {
        this(heading, x, y, power, ownerName, victimName, isActive, (long) -1);
        this.bulletId = bulletId;
    }

    private int bulletId = -1;

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

    @Override public boolean equals(Object o) {
        return o == this || (bulletId >= 0 && o instanceof Bullet && ((Bullet) o).bulletId == bulletId);
    }
    @Override public int hashCode() { return bulletId >= 0 ? bulletId : System.identityHashCode(this); }
}
