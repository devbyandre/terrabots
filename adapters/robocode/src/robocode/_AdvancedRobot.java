package robocode;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Vector;

/**
 * Robocode's AdvancedRobot API, declared here and inherited by AdvancedRobot.
 * Robocode splits it over _AdvancedRobot, _AdvancedRadiansRobot and
 * AdvancedRobot; compiled bots name whichever class declared a method, so all
 * three exist, and the methods live on the lowest one so every lookup finds them.
 */
public class _AdvancedRobot extends Robot {

    // --- queued commands ----------------------------------------------------------
    public void setAhead(double distance) { peer.distance = distance; }
    public void setBack(double distance) { peer.distance = -distance; }
    public void setTurnRight(double degrees) { peer.bodyTurn = degrees; }
    public void setTurnLeft(double degrees) { peer.bodyTurn = -degrees; }
    public void setTurnRightRadians(double radians) { peer.bodyTurn = Math.toDegrees(radians); }
    public void setTurnLeftRadians(double radians) { peer.bodyTurn = -Math.toDegrees(radians); }
    public void setTurnGunRight(double degrees) { peer.gunTurn = degrees; }
    public void setTurnGunLeft(double degrees) { peer.gunTurn = -degrees; }
    public void setTurnGunRightRadians(double radians) { peer.gunTurn = Math.toDegrees(radians); }
    public void setTurnGunLeftRadians(double radians) { peer.gunTurn = -Math.toDegrees(radians); }
    public void setTurnRadarRight(double degrees) { peer.radarTurn = degrees; }
    public void setTurnRadarLeft(double degrees) { peer.radarTurn = -degrees; }
    public void setTurnRadarRightRadians(double radians) { peer.radarTurn = Math.toDegrees(radians); }
    public void setTurnRadarLeftRadians(double radians) { peer.radarTurn = -Math.toDegrees(radians); }
    public void setFire(double power) { peer.queueFire(power); }
    public Bullet setFireBullet(double power) { return peer.queueFire(power); }
    public void setMaxVelocity(double velocity) { peer.maxVelocity = Math.min(Rules.MAX_VELOCITY, Math.abs(velocity)); }
    public void setMaxTurnRate(double degrees) { peer.maxTurnRate = Math.min(Rules.MAX_TURN_RATE, Math.abs(degrees)); }
    public void setMaxTurnRateRadians(double radians) { setMaxTurnRate(Math.toDegrees(radians)); }
    public void execute() { peer.execute(); }
    public void setStop() { setStop(false); }
    public void setStop(boolean overwrite) {
        if (peer.stopped == null || overwrite) {
            peer.stopped = new double[] {peer.distance, peer.bodyTurn, peer.gunTurn, peer.radarTurn};
        }
        peer.distance = peer.bodyTurn = peer.gunTurn = peer.radarTurn = 0;
    }
    public void setResume() {
        if (peer.stopped != null) {
            peer.distance = peer.stopped[0]; peer.bodyTurn = peer.stopped[1];
            peer.gunTurn = peer.stopped[2]; peer.radarTurn = peer.stopped[3];
            peer.stopped = null;
        }
    }

    // --- blocking, in radians ------------------------------------------------------
    public void turnRightRadians(double radians) { turnRight(Math.toDegrees(radians)); }
    public void turnLeftRadians(double radians) { turnLeft(Math.toDegrees(radians)); }
    public void turnGunRightRadians(double radians) { turnGunRight(Math.toDegrees(radians)); }
    public void turnGunLeftRadians(double radians) { turnGunLeft(Math.toDegrees(radians)); }
    public void turnRadarRightRadians(double radians) { turnRadarRight(Math.toDegrees(radians)); }
    public void turnRadarLeftRadians(double radians) { turnRadarLeft(Math.toDegrees(radians)); }

    // --- status ---------------------------------------------------------------------
    public double getDistanceRemaining() { return peer.distance; }
    public double getTurnRemaining() { return peer.bodyTurn; }
    public double getTurnRemainingRadians() { return Math.toRadians(peer.bodyTurn); }
    public double getGunTurnRemaining() { return peer.gunTurn; }
    public double getGunTurnRemainingRadians() { return Math.toRadians(peer.gunTurn); }
    public double getRadarTurnRemaining() { return peer.radarTurn; }
    public double getRadarTurnRemainingRadians() { return Math.toRadians(peer.radarTurn); }
    public double getHeadingRadians() { return Math.toRadians(peer.heading); }
    public double getGunHeadingRadians() { return Math.toRadians(peer.gunHeading); }
    public double getRadarHeadingRadians() { return Math.toRadians(peer.radarHeading); }

    // --- events ---------------------------------------------------------------------
    public void addCustomEvent(Condition condition) { peer.conditions.add(condition); }
    public void removeCustomEvent(Condition condition) { peer.conditions.remove(condition); }
    public void clearAllEvents() { peer.pending.clear(); }
    public Vector<Event> getAllEvents() { return new Vector<>(peer.allEvents()); }
    public void setEventPriority(String eventClass, int priority) { peer.priorities.put(eventClass, priority); }
    public int getEventPriority(String eventClass) {
        Integer p = peer.priorities.get(eventClass);
        return p != null ? p : 0;
    }
    public void setInterruptible(boolean interruptible) { peer.interruptible = interruptible; }
    public void waitFor(Condition condition) {
        while (!condition.test()) peer.execute();
    }

    private <T extends Event> Vector<T> eventsOf(Class<T> type) {
        Vector<T> out = new Vector<>();
        for (Event e : peer.allEvents()) if (type.isInstance(e)) out.add(type.cast(e));
        return out;
    }
    public Vector<ScannedRobotEvent> getScannedRobotEvents() { return eventsOf(ScannedRobotEvent.class); }
    public Vector<HitByBulletEvent> getHitByBulletEvents() { return eventsOf(HitByBulletEvent.class); }
    public Vector<BulletHitEvent> getBulletHitEvents() { return eventsOf(BulletHitEvent.class); }
    public Vector<BulletMissedEvent> getBulletMissedEvents() { return eventsOf(BulletMissedEvent.class); }
    public Vector<BulletHitBulletEvent> getBulletHitBulletEvents() { return eventsOf(BulletHitBulletEvent.class); }
    public Vector<HitWallEvent> getHitWallEvents() { return eventsOf(HitWallEvent.class); }
    public Vector<HitRobotEvent> getHitRobotEvents() { return eventsOf(HitRobotEvent.class); }
    public Vector<RobotDeathEvent> getRobotDeathEvents() { return eventsOf(RobotDeathEvent.class); }
    public List<StatusEvent> getStatusEvents() { return new ArrayList<>(eventsOf(StatusEvent.class)); }

    // Robocode 1.0 names, still used by old bots
    @Deprecated public void endTurn() { execute(); }
    @Deprecated public void setTurnLeftDegrees(double d) { setTurnLeft(d); }
    @Deprecated public void setTurnRightDegrees(double d) { setTurnRight(d); }
    @Deprecated public void setTurnGunLeftDegrees(double d) { setTurnGunLeft(d); }
    @Deprecated public void setTurnGunRightDegrees(double d) { setTurnGunRight(d); }
    @Deprecated public void setTurnRadarLeftDegrees(double d) { setTurnRadarLeft(d); }
    @Deprecated public void setTurnRadarRightDegrees(double d) { setTurnRadarRight(d); }
    @Deprecated public int getMaxWaitCount() { return 10000; }
    @Deprecated public int getWaitCount() { return 0; }

    // --- data files (inside the sandbox: an in-memory folder, gone after the battle) ----
    public File getDataDirectory() {
        File dir = new File("/data", getClass().getName());
        dir.mkdirs();
        return dir;
    }
    public File getDataFile(String name) { return new File(getDataDirectory(), name); }
    public long getDataQuotaAvailable() {
        long used = 0;
        File[] files = getDataDirectory().listFiles();
        if (files != null) for (File f : files) used += f.length();
        return Math.max(0, peer.quotaBytes - used);
    }
}
