package tbtest;

import robocode.AdvancedRobot;
import robocode.ScannedRobotEvent;

/** Builds its helper once, in round 1, with the round-1 robot, and keeps using it (like many top bots). */
public class Keeper extends AdvancedRobot {
    static Helper helper;

    static final class Helper {
        final AdvancedRobot bot;
        Helper(AdvancedRobot bot) { this.bot = bot; }
        void spin() { bot.setTurnRadarRight(Double.POSITIVE_INFINITY); }
        void shoot(ScannedRobotEvent e) {
            bot.setTurnGunRight(robocode.util.Utils.normalRelativeAngleDegrees(
                    bot.getHeading() + e.getBearing() - bot.getGunHeading()));
            bot.setFire(2);
        }
    }

    @Override
    public void run() {
        if (getRoundNum() == 0) helper = new Helper(this);
        setAdjustRadarForGunTurn(true);
        helper.spin();
        while (true) execute();
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) { helper.shoot(e); }
}
