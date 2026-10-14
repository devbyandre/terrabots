package tbtest;

import robocode.HitWallEvent;
import robocode.Robot;
import robocode.ScannedRobotEvent;

/** Basic Robot (blocking calls): walks, spins its gun, fires at what it sees. */
public class Walker extends Robot {
    @Override
    public void run() {
        while (true) {
            ahead(100);
            turnGunRight(360);
            back(100);
            turnGunRight(360);
        }
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) { fire(1); }

    @Override
    public void onHitWall(HitWallEvent e) { turnRight(90 - e.getBearing()); }
}
