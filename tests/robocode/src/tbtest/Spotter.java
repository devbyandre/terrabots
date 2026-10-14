package tbtest;

import java.io.IOException;

import robocode.ScannedRobotEvent;
import robocode.TeamRobot;

/** TeamRobot: spins its radar and tells the team where enemies are (x, y). */
public class Spotter extends TeamRobot {
    @Override
    public void run() {
        setAdjustRadarForGunTurn(true);
        setTurnRadarRight(Double.POSITIVE_INFINITY);
        while (true) execute();
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {
        if (isTeammate(e.getName())) return;
        double a = Math.toRadians(getHeading() + e.getBearing());
        try {
            broadcastMessage(new double[] {getX() + Math.sin(a) * e.getDistance(), getY() + Math.cos(a) * e.getDistance()});
        } catch (IOException ignored) {
        }
    }
}
