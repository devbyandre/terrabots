package robocode;

/** Robocode's BulletMissedEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class BulletMissedEvent extends Event {
    private final Bullet bullet;

    public BulletMissedEvent(Bullet bullet) {
        this.bullet = bullet;
    }

    public Bullet getBullet() { return bullet; }

    @Override
    int defaultPriority() { return 60; }

    @Override
    void dispatch(_Peer p) { if (p.basic != null) p.basic.onBulletMissed(this); }
}
