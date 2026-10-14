package robocode;

import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.io.File;
import java.io.IOException;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import robocode.robotinterfaces.peer.ITeamRobotPeer;

/**
 * Internal: Robocode's peer interfaces on top of _Peer, for bots that implement
 * robocode.robotinterfaces directly instead of extending Robot. Angles in
 * radians here, as in Robocode's peer API.
 */
public final class _PeerAdapter implements ITeamRobotPeer {
    final _Peer peer;
    private Graphics2D graphics;

    _PeerAdapter(_Peer peer) { this.peer = peer; }

    @Override public String getName() { return peer.name; }
    @Override public long getTime() { return peer.time; }
    @Override public double getEnergy() { return peer.currentEnergy(); }
    @Override public double getX() { return peer.x; }
    @Override public double getY() { return peer.y; }
    @Override public double getVelocity() { return peer.velocity; }
    @Override public double getBodyHeading() { return Math.toRadians(peer.heading); }
    @Override public double getGunHeading() { return Math.toRadians(peer.gunHeading); }
    @Override public double getRadarHeading() { return Math.toRadians(peer.radarHeading); }
    @Override public double getGunHeat() { return peer.currentGunHeat(); }
    @Override public double getBattleFieldWidth() { return peer.fieldW; }
    @Override public double getBattleFieldHeight() { return peer.fieldH; }
    @Override public int getOthers() { return peer.others; }
    @Override public int getNumSentries() { return 0; }
    @Override public int getNumRounds() { return peer.numRounds; }
    @Override public int getRoundNum() { return peer.roundNum; }
    @Override public int getSentryBorderSize() { return 100; }
    @Override public double getGunCoolingRate() { return peer.coolingRate; }
    @Override public double getDistanceRemaining() { return peer.distance; }
    @Override public double getBodyTurnRemaining() { return Math.toRadians(peer.bodyTurn); }
    @Override public double getGunTurnRemaining() { return Math.toRadians(peer.gunTurn); }
    @Override public double getRadarTurnRemaining() { return Math.toRadians(peer.radarTurn); }

    @Override public void execute() { peer.execute(); }
    @Override public void move(double distance) { peer.distance = distance; while (peer.distance != 0) peer.execute(); }
    @Override public void turnBody(double radians) { peer.bodyTurn = Math.toDegrees(radians); while (peer.bodyTurn != 0) peer.execute(); }
    @Override public void turnGun(double radians) { peer.gunTurn = Math.toDegrees(radians); while (peer.gunTurn != 0) peer.execute(); }
    @Override public void turnRadar(double radians) { peer.radarTurn = Math.toDegrees(radians); while (peer.radarTurn != 0) peer.execute(); }
    @Override public Bullet fire(double power) { Bullet b = peer.queueFire(power); peer.execute(); return b; }
    @Override public Bullet setFire(double power) { return peer.queueFire(power); }
    @Override public void setBodyColor(Color color) { }
    @Override public void setGunColor(Color color) { }
    @Override public void setRadarColor(Color color) { }
    @Override public void setBulletColor(Color color) { }
    @Override public void setScanColor(Color color) { }
    @Override public void getCall() { }
    @Override public void setCall() { }
    @Override public Graphics2D getGraphics() {
        if (graphics == null) graphics = new BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB).createGraphics();
        return graphics;
    }
    @Override public void setDebugProperty(String key, String value) { }
    /** Robocode: scan again and end the turn; a running onScannedRobot may be interrupted by the new scan. */
    @Override public void rescan() {
        boolean was = peer.interruptible;
        if (peer.currentPriority == 10) peer.interruptible = true;
        peer.execute();
        peer.interruptible = was;
    }

    @Override public void stop(boolean overwrite) { setStop(overwrite); peer.execute(); }
    @Override public void resume() { setResume(); peer.execute(); }
    @Override public void setAdjustGunForBodyTurn(boolean independent) { peer.adjGun = independent; }
    @Override public void setAdjustRadarForGunTurn(boolean independent) { peer.adjRadar = independent; }
    @Override public void setAdjustRadarForBodyTurn(boolean independent) { peer.adjRadarRobot = independent; }
    @Override public boolean isAdjustGunForBodyTurn() { return peer.adjGun; }
    @Override public boolean isAdjustRadarForGunTurn() { return peer.adjRadar; }
    @Override public boolean isAdjustRadarForBodyTurn() { return peer.adjRadarRobot; }

    @Override public void setStop(boolean overwrite) {
        if (peer.stopped == null || overwrite) {
            peer.stopped = new double[] {peer.distance, peer.bodyTurn, peer.gunTurn, peer.radarTurn};
        }
        peer.distance = peer.bodyTurn = peer.gunTurn = peer.radarTurn = 0;
    }
    @Override public void setResume() {
        if (peer.stopped != null) {
            peer.distance = peer.stopped[0]; peer.bodyTurn = peer.stopped[1];
            peer.gunTurn = peer.stopped[2]; peer.radarTurn = peer.stopped[3];
            peer.stopped = null;
        }
    }
    @Override public void setMove(double distance) { peer.distance = distance; }
    @Override public void setTurnBody(double radians) { peer.bodyTurn = Math.toDegrees(radians); }
    @Override public void setTurnGun(double radians) { peer.gunTurn = Math.toDegrees(radians); }
    @Override public void setTurnRadar(double radians) { peer.radarTurn = Math.toDegrees(radians); }
    @Override public void setMaxTurnRate(double radians) { peer.maxTurnRate = Math.min(Rules.MAX_TURN_RATE, Math.abs(Math.toDegrees(radians))); }
    @Override public void setMaxVelocity(double velocity) { peer.maxVelocity = Math.min(Rules.MAX_VELOCITY, Math.abs(velocity)); }
    @Override public void waitFor(Condition condition) { while (!condition.test()) peer.execute(); }
    @Override public void setInterruptible(boolean interruptible) { peer.interruptible = interruptible; }
    @Override public void setEventPriority(String eventClass, int priority) { peer.priorities.put(eventClass, priority); }
    @Override public int getEventPriority(String eventClass) {
        Integer p = peer.priorities.get(eventClass);
        return p != null ? p : 0;
    }
    @Override public void addCustomEvent(Condition condition) { peer.conditions.add(condition); }
    @Override public void removeCustomEvent(Condition condition) { peer.conditions.remove(condition); }
    @Override public void clearAllEvents() { peer.pending.clear(); }
    @Override public List<Event> getAllEvents() { return peer.allEvents(); }

    private <T extends Event> List<T> of(Class<T> type) {
        List<T> out = new ArrayList<>();
        for (Event e : peer.allEvents()) if (type.isInstance(e)) out.add(type.cast(e));
        return out;
    }
    @Override public List<StatusEvent> getStatusEvents() { return of(StatusEvent.class); }
    @Override public List<BulletMissedEvent> getBulletMissedEvents() { return of(BulletMissedEvent.class); }
    @Override public List<BulletHitBulletEvent> getBulletHitBulletEvents() { return of(BulletHitBulletEvent.class); }
    @Override public List<BulletHitEvent> getBulletHitEvents() { return of(BulletHitEvent.class); }
    @Override public List<HitByBulletEvent> getHitByBulletEvents() { return of(HitByBulletEvent.class); }
    @Override public List<HitRobotEvent> getHitRobotEvents() { return of(HitRobotEvent.class); }
    @Override public List<HitWallEvent> getHitWallEvents() { return of(HitWallEvent.class); }
    @Override public List<RobotDeathEvent> getRobotDeathEvents() { return of(RobotDeathEvent.class); }
    @Override public List<ScannedRobotEvent> getScannedRobotEvents() { return of(ScannedRobotEvent.class); }
    @Override public List<MessageEvent> getMessageEvents() { return of(MessageEvent.class); }

    @Override public File getDataDirectory() {
        File dir = new File("/data", peer.robot.getClass().getName());
        dir.mkdirs();
        return dir;
    }
    @Override public File getDataFile(String filename) { return new File(getDataDirectory(), filename); }
    @Override public long getDataQuotaAvailable() {
        long used = 0;
        File[] files = getDataDirectory().listFiles();
        if (files != null) for (File f : files) used += f.length();
        return Math.max(0, peer.quotaBytes - used);
    }

    @Override public String[] getTeammates() {
        return peer.teammates.isEmpty() ? null : peer.teammates.values().toArray(new String[0]);
    }
    @Override public boolean isTeammate(String name) { return peer.teammates.containsValue(name); }
    @Override public void broadcastMessage(Serializable message) throws IOException { peer.queueMessage(null, message); }
    @Override public void sendMessage(String name, Serializable message) throws IOException {
        for (Map.Entry<Integer, String> e : peer.teammates.entrySet()) {
            if (e.getValue().equals(name)) peer.queueMessage(e.getKey(), message);
        }
    }
}
