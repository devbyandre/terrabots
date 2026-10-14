package robocode.robotinterfaces.peer;

import java.io.File;
import java.util.List;

import robocode.*;

public interface IAdvancedRobotPeer extends IStandardRobotPeer {
    boolean isAdjustGunForBodyTurn();
    boolean isAdjustRadarForGunTurn();
    boolean isAdjustRadarForBodyTurn();
    void setStop(boolean overwrite);
    void setResume();
    void setMove(double distance);
    void setTurnBody(double radians);
    void setTurnGun(double radians);
    void setTurnRadar(double radians);
    void setMaxTurnRate(double newMaxTurnRate);
    void setMaxVelocity(double newMaxVelocity);
    void waitFor(Condition condition);
    void setInterruptible(boolean interruptible);
    void setEventPriority(String eventClass, int priority);
    int getEventPriority(String eventClass);
    void addCustomEvent(Condition condition);
    void removeCustomEvent(Condition condition);
    void clearAllEvents();
    List<Event> getAllEvents();
    List<StatusEvent> getStatusEvents();
    List<BulletMissedEvent> getBulletMissedEvents();
    List<BulletHitBulletEvent> getBulletHitBulletEvents();
    List<BulletHitEvent> getBulletHitEvents();
    List<HitByBulletEvent> getHitByBulletEvents();
    List<HitRobotEvent> getHitRobotEvents();
    List<HitWallEvent> getHitWallEvents();
    List<RobotDeathEvent> getRobotDeathEvents();
    List<ScannedRobotEvent> getScannedRobotEvents();
    File getDataDirectory();
    File getDataFile(String filename);
    long getDataQuotaAvailable();
}
