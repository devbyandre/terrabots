package robocode;

/** Robocode's BulletHitBulletEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class BulletHitBulletEvent extends Event {
    private final Bullet bullet;
    private final Bullet hitBullet;

    public BulletHitBulletEvent(Bullet bullet, Bullet hitBullet) {
        this.bullet = bullet;
        this.hitBullet = hitBullet;
    }

    public Bullet getBullet() { return bullet; }
    public Bullet getHitBullet() { return hitBullet; }

    @Override
    int defaultPriority() { return 55; }

    @Override
    void dispatch(_Peer p) { if (p.basic != null) p.basic.onBulletHitBullet(this); }
}
