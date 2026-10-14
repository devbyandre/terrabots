package robocode;

/** Robocode's BulletHitEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class BulletHitEvent extends Event {
    private final String name;
    private final double energy;
    private final Bullet bullet;

    public BulletHitEvent(String name, double energy, Bullet bullet) {
        this.name = name;
        this.energy = energy;
        this.bullet = bullet;
    }

    public String getName() { return name; }
    public double getEnergy() { return energy; }
    public Bullet getBullet() { return bullet; }

    @Override
    int defaultPriority() { return 50; }

    @Override
    void dispatch(Robot r) { r.onBulletHit(this); }
}
