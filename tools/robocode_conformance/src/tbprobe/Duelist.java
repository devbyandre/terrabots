package tbprobe;

import robocode.*;
import robocode.util.Utils;

/** Deterministic fighter: radar lock, head-on gun, scripted zig-zag; logs every turn. */
public class Duelist extends AdvancedRobot {
    private final StringBuilder log = new StringBuilder();
    private void log(String what) { log.append(String.format("P %d %s%n", getTime(), what)); }
    private void save() {
        out.print(log);
        try (java.io.PrintStream f = new java.io.PrintStream(new RobocodeFileOutputStream(getDataFile("probe-" + getName().replaceAll("[^0-9]", "") + ".log")))) {
            f.print(log);
        } catch (java.io.IOException e) { out.println("can't save: " + e); }
    }

    @Override
    public void run() {
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        setTurnRadarRight(Double.POSITIVE_INFINITY);
        while (true) {
            long t = getTime();
            log(String.format("x=%.4f y=%.4f h=%.4f v=%.4f g=%.4f r=%.4f e=%.4f heat=%.4f",
                    getX(), getY(), getHeading(), getVelocity(), getGunHeading(), getRadarHeading(), getEnergy(), getGunHeat()));
            if (t % 25 == 0) setAhead((t / 25) % 2 == 0 ? 120 : -120);
            setTurnRight(t % 40 < 20 ? 5 : -5);
            execute();
        }
    }

    @Override public void onScannedRobot(ScannedRobotEvent e) {
        double abs = getHeadingRadians() + e.getBearingRadians();
        setTurnRadarRightRadians(Utils.normalRelativeAngle(abs - getRadarHeadingRadians()) * 2);
        setTurnGunRightRadians(Utils.normalRelativeAngle(abs - getGunHeadingRadians()));
        if (getGunHeat() == 0 && Math.abs(getGunTurnRemaining()) < 10) setFire(e.getDistance() < 250 ? 2.5 : 1.5);
        log(String.format("scan b=%.4f dist=%.4f h=%.4f v=%.4f e=%.4f", e.getBearing(), e.getDistance(), e.getHeading(), e.getVelocity(), e.getEnergy()));
    }
    @Override public void onBulletHit(BulletHitEvent e) { log(String.format("hit x=%.4f y=%.4f p=%.2f en=%.4f", e.getBullet().getX(), e.getBullet().getY(), e.getBullet().getPower(), e.getEnergy())); }
    @Override public void onHitByBullet(HitByBulletEvent e) { log(String.format("hitby b=%.4f p=%.2f", e.getBearing(), e.getPower())); }
    @Override public void onBulletMissed(BulletMissedEvent e) { log(String.format("miss x=%.4f y=%.4f", e.getBullet().getX(), e.getBullet().getY())); }
    @Override public void onBulletHitBullet(BulletHitBulletEvent e) { log(String.format("bhb x=%.4f y=%.4f ox=%.4f oy=%.4f", e.getBullet().getX(), e.getBullet().getY(), e.getHitBullet().getX(), e.getHitBullet().getY())); }
    @Override public void onHitWall(HitWallEvent e) { log(String.format("wall b=%.4f", e.getBearing())); }
    @Override public void onHitRobot(HitRobotEvent e) { log(String.format("ram b=%.4f fault=%b", e.getBearing(), e.isMyFault())); }
    @Override public void onRobotDeath(RobotDeathEvent e) { log("enemydeath"); }
    @Override public void onWin(WinEvent e) { log("win"); }
    @Override public void onDeath(DeathEvent e) { log("death"); save(); }
    @Override public void onRoundEnded(RoundEndedEvent e) { log("end"); save(); }
}
