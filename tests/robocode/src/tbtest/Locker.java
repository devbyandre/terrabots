package tbtest;

import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.util.HashMap;

import robocode.AdvancedRobot;
import robocode.BulletHitEvent;
import robocode.RoundEndedEvent;
import robocode.ScannedRobotEvent;
import robocode.util.Utils;

/** AdvancedRobot: radar lock, linear aim, strafing; counts hits across rounds in a data file. */
public class Locker extends AdvancedRobot {
    static int hits;          // static fields survive rounds, as in Robocode

    @Override
    public void run() {
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        setTurnRadarRightRadians(Double.POSITIVE_INFINITY);
        while (true) execute();
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {
        double abs = getHeadingRadians() + e.getBearingRadians();
        setTurnRadarRightRadians(Utils.normalRelativeAngle(abs - getRadarHeadingRadians()) * 2);
        double lateral = e.getVelocity() * Math.sin(e.getHeadingRadians() - abs);
        setTurnGunRightRadians(Utils.normalRelativeAngle(abs - getGunHeadingRadians() + lateral / 14));
        setFire(2);
        setTurnRightRadians(Utils.normalRelativeAngle(e.getBearingRadians() + Math.PI / 2));
        setAhead(100 * (getTime() / 40 % 2 == 0 ? 1 : -1));
    }

    @Override
    public void onBulletHit(BulletHitEvent e) { hits++; }

    @Override
    public void onRoundEnded(RoundEndedEvent e) {
        try (ObjectOutputStream out = new ObjectOutputStream(new robocode.RobocodeFileOutputStream(getDataFile("hits")))) {
            out.writeObject(new HashMap<>(java.util.Map.of("hits", hits)));
        } catch (IOException ex) {
            out.println("can't save: " + ex);
        }
        out.println("round " + e.getRound() + " hits so far " + hits);
    }
}
