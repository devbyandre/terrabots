package tbprobe;

import robocode.*;

/** A fixed script of moves; prints its state every turn, for comparing two engines. */
public class Probe extends AdvancedRobot {
    private final StringBuilder log = new StringBuilder();

    private void log(String what) {
        log.append(String.format("P %d %s%n", getTime(), what));
    }

    private void save() {
        out.print(log);
        try (java.io.PrintStream f = new java.io.PrintStream(new RobocodeFileOutputStream(getDataFile("probe.log")))) {
            f.print(log);
        } catch (java.io.IOException e) {
            out.println("can't save: " + e);
        }
    }

    @Override public void onDeath(DeathEvent e) { log("death"); save(); }
    @Override public void onRoundEnded(RoundEndedEvent e) { log("end"); save(); }

    @Override
    public void run() {
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        while (true) {
            long t = getTime();
            log(String.format("x=%.4f y=%.4f h=%.4f v=%.4f g=%.4f r=%.4f e=%.4f heat=%.4f d=%.4f",
                    getX(), getY(), getHeading(), getVelocity(), getGunHeading(), getRadarHeading(),
                    getEnergy(), getGunHeat(), getDistanceRemaining()));
            if (t == 0) setAhead(1000);
            if (t == 10) setTurnRight(90);
            if (t == 30) setBack(1000);
            if (t == 45) setTurnLeft(60);
            if (t == 55) setMaxVelocity(4);
            if (t == 70) { setMaxVelocity(8); setAhead(40); }
            setTurnGunRight(t < 40 ? 7 : -5);
            setTurnRadarRight(30);
            if (t == 32) setFire(2);
            if (t == 61) setFire(0.5);
            if (t == 90) setFire(3);
            if (t >= 120) { setStop(); }
            execute();
        }
    }

    @Override public void onScannedRobot(ScannedRobotEvent e) {
        log(String.format("scan b=%.4f dist=%.4f h=%.4f v=%.4f e=%.4f", e.getBearing(), e.getDistance(), e.getHeading(), e.getVelocity(), e.getEnergy()));
    }
    @Override public void onBulletHit(BulletHitEvent e) {
        log(String.format("hit x=%.4f y=%.4f p=%.2f", e.getBullet().getX(), e.getBullet().getY(), e.getBullet().getPower()));
    }
    @Override public void onBulletMissed(BulletMissedEvent e) {
        log(String.format("miss x=%.4f y=%.4f p=%.2f", e.getBullet().getX(), e.getBullet().getY(), e.getBullet().getPower()));
    }
    @Override public void onHitWall(HitWallEvent e) { log(String.format("wall b=%.4f", e.getBearing())); }
    @Override public void onHitRobot(HitRobotEvent e) { log(String.format("ram b=%.4f", e.getBearing())); }
}
