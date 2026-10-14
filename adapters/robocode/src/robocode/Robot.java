package robocode;

import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.io.PrintStream;

import robocode.robotinterfaces.IBasicEvents3;
import robocode.robotinterfaces.IPaintEvents;

/** Robocode's basic Robot: blocking commands (ahead(100) waits until done). */
public class Robot extends _Robot implements Runnable, IBasicEvents3, IPaintEvents {
    public PrintStream out = System.err;
    private Graphics2D graphics;

    public Robot() { }

    @Override
    public void run() { }

    // --- status -----------------------------------------------------------
    public String getName() { return peer.name; }
    public double getX() { return peer.x; }
    public double getY() { return peer.y; }
    public double getHeading() { return peer.heading; }
    public double getGunHeading() { return peer.gunHeading; }
    public double getRadarHeading() { return peer.radarHeading; }
    public double getEnergy() { return peer.energy; }
    public double getGunHeat() { return peer.gunHeat; }
    public double getGunCoolingRate() { return peer.coolingRate; }
    public double getVelocity() { return peer.velocity; }
    public double getBattleFieldWidth() { return peer.fieldW; }
    public double getBattleFieldHeight() { return peer.fieldH; }
    public double getWidth() { return 36; }
    public double getHeight() { return 36; }
    public int getOthers() { return peer.others; }
    public int getNumSentries() { return 0; }
    public int getSentryBorderSize() { return 100; }
    public int getNumRounds() { return peer.numRounds; }
    public int getRoundNum() { return peer.roundNum; }
    public long getTime() { return peer.time; }

    // --- blocking commands --------------------------------------------------
    public void ahead(double distance) {
        peer.distance = distance;
        while (peer.distance != 0) peer.execute();
    }
    public void back(double distance) { ahead(-distance); }
    public void turnRight(double degrees) {
        peer.bodyTurn = degrees;
        while (peer.bodyTurn != 0) peer.execute();
    }
    public void turnLeft(double degrees) { turnRight(-degrees); }
    public void turnGunRight(double degrees) {
        peer.gunTurn = degrees;
        while (peer.gunTurn != 0) peer.execute();
    }
    public void turnGunLeft(double degrees) { turnGunRight(-degrees); }
    public void turnRadarRight(double degrees) {
        peer.radarTurn = degrees;
        while (peer.radarTurn != 0) peer.execute();
    }
    public void turnRadarLeft(double degrees) { turnRadarRight(-degrees); }
    public void fire(double power) {
        peer.queueFire(power);
        peer.execute();
    }
    public Bullet fireBullet(double power) {
        Bullet b = peer.queueFire(power);
        peer.execute();
        return b;
    }
    public void doNothing() { peer.execute(); }
    public void scan() { peer.execute(); }
    public void stop() { stop(false); }
    public void stop(boolean overwrite) {
        if (peer.stopped == null || overwrite) {
            peer.stopped = new double[] {peer.distance, peer.bodyTurn, peer.gunTurn, peer.radarTurn};
        }
        peer.distance = peer.bodyTurn = peer.gunTurn = peer.radarTurn = 0;
        peer.execute();
    }
    public void resume() {
        if (peer.stopped != null) {
            peer.distance = peer.stopped[0]; peer.bodyTurn = peer.stopped[1];
            peer.gunTurn = peer.stopped[2]; peer.radarTurn = peer.stopped[3];
            peer.stopped = null;
        }
        peer.execute();
    }

    // --- independent gun and radar -------------------------------------------
    public void setAdjustGunForRobotTurn(boolean independent) { peer.adjGun = independent; }
    public void setAdjustRadarForGunTurn(boolean independent) { peer.adjRadar = independent; }
    public void setAdjustRadarForRobotTurn(boolean independent) { peer.adjRadarRobot = independent; }
    public boolean isAdjustGunForRobotTurn() { return peer.adjGun; }
    public boolean isAdjustRadarForGunTurn() { return peer.adjRadar; }
    public boolean isAdjustRadarForRobotTurn() { return peer.adjRadarRobot; }

    // --- looks (not shown by the Terrabots viewer yet) -------------------------
    public void setColors(Color body, Color gun, Color radar) { }
    public void setColors(Color body, Color gun, Color radar, Color bullet, Color scan) { }
    public void setAllColors(Color color) { }
    public void setBodyColor(Color color) { }
    public void setGunColor(Color color) { }
    public void setRadarColor(Color color) { }
    public void setBulletColor(Color color) { }
    public void setScanColor(Color color) { }
    public void setDebugProperty(String key, String value) { }

    public Graphics2D getGraphics() {
        if (graphics == null) graphics = new BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB).createGraphics();
        return graphics;
    }

    // --- events (override these) -----------------------------------------------
    @Override public void onStatus(StatusEvent e) { }
    @Override public void onBulletHit(BulletHitEvent e) { }
    @Override public void onBulletHitBullet(BulletHitBulletEvent e) { }
    @Override public void onBulletMissed(BulletMissedEvent e) { }
    @Override public void onDeath(DeathEvent e) { }
    @Override public void onHitByBullet(HitByBulletEvent e) { }
    @Override public void onHitRobot(HitRobotEvent e) { }
    @Override public void onHitWall(HitWallEvent e) { }
    @Override public void onScannedRobot(ScannedRobotEvent e) { }
    @Override public void onRobotDeath(RobotDeathEvent e) { }
    @Override public void onWin(WinEvent e) { }
    @Override public void onBattleEnded(BattleEndedEvent e) { }
    @Override public void onRoundEnded(RoundEndedEvent e) { }
    @Override public void onPaint(Graphics2D g) { }
}
