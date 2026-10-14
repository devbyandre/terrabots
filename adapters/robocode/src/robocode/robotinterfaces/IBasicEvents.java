package robocode.robotinterfaces;

import robocode.*;

public interface IBasicEvents {
    void onStatus(StatusEvent event);
    void onBulletHit(BulletHitEvent event);
    void onBulletHitBullet(BulletHitBulletEvent event);
    void onBulletMissed(BulletMissedEvent event);
    void onDeath(DeathEvent event);
    void onHitByBullet(HitByBulletEvent event);
    void onHitRobot(HitRobotEvent event);
    void onHitWall(HitWallEvent event);
    void onScannedRobot(ScannedRobotEvent event);
    void onRobotDeath(RobotDeathEvent event);
    void onWin(WinEvent event);
}
