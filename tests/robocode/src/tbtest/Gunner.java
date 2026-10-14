package tbtest;

import robocode.Droid;
import robocode.MessageEvent;
import robocode.TeamRobot;
import robocode.util.Utils;

/** Droid (no radar): aims only at the positions its Spotter sends. */
public class Gunner extends TeamRobot implements Droid {
    @Override
    public void run() {
        setAdjustGunForRobotTurn(true);
        while (true) execute();
    }

    @Override
    public void onMessageReceived(MessageEvent e) {
        double[] p = (double[]) e.getMessage();
        double aim = Math.atan2(p[0] - getX(), p[1] - getY());
        setTurnGunRightRadians(Utils.normalRelativeAngle(aim - getGunHeadingRadians()));
        if (Math.abs(getGunTurnRemaining()) < 3) setFire(1);
    }
}
