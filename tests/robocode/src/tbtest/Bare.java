package tbtest;

import java.io.PrintStream;

import robocode.*;
import robocode.robotinterfaces.IAdvancedEvents;
import robocode.robotinterfaces.IAdvancedRobot;
import robocode.robotinterfaces.IBasicEvents;
import robocode.robotinterfaces.peer.IAdvancedRobotPeer;
import robocode.robotinterfaces.peer.IBasicRobotPeer;
import robocode.util.Utils;

/** Built on robocode.robotinterfaces only (no Robot class), talking to the peer directly. */
public class Bare implements IAdvancedRobot, IBasicEvents, IAdvancedEvents, Runnable {
    private IAdvancedRobotPeer peer;
    private PrintStream out;

    @Override public void setPeer(IBasicRobotPeer p) { peer = (IAdvancedRobotPeer) p; }
    @Override public void setOut(PrintStream o) { out = o; }
    @Override public Runnable getRobotRunnable() { return this; }
    @Override public IBasicEvents getBasicEventListener() { return this; }
    @Override public IAdvancedEvents getAdvancedEventListener() { return this; }

    @Override
    public void run() {
        peer.setAdjustGunForBodyTurn(true);
        peer.setAdjustRadarForGunTurn(true);
        peer.setTurnRadar(Double.POSITIVE_INFINITY);
        while (true) peer.execute();
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {
        double abs = peer.getBodyHeading() + e.getBearingRadians();
        peer.setTurnRadar(Utils.normalRelativeAngle(abs - peer.getRadarHeading()) * 2);
        peer.setTurnGun(Utils.normalRelativeAngle(abs - peer.getGunHeading()));
        peer.setFire(2);
    }

    @Override public void onStatus(StatusEvent e) { }
    @Override public void onBulletHit(BulletHitEvent e) { }
    @Override public void onBulletHitBullet(BulletHitBulletEvent e) { }
    @Override public void onBulletMissed(BulletMissedEvent e) { }
    @Override public void onDeath(DeathEvent e) { }
    @Override public void onHitByBullet(HitByBulletEvent e) { }
    @Override public void onHitRobot(HitRobotEvent e) { }
    @Override public void onHitWall(HitWallEvent e) { }
    @Override public void onRobotDeath(RobotDeathEvent e) { }
    @Override public void onWin(WinEvent e) { }
    @Override public void onSkippedTurn(SkippedTurnEvent e) { }
    @Override public void onCustomEvent(CustomEvent e) { }
}
