package robocode.robotinterfaces.peer;

import java.awt.Color;
import java.awt.Graphics2D;

import robocode.Bullet;

/** Robocode's robot peer: what a robot can ask and command (angles in radians). */
public interface IBasicRobotPeer {
    String getName();
    long getTime();
    double getEnergy();
    double getX();
    double getY();
    double getVelocity();
    double getBodyHeading();
    double getGunHeading();
    double getRadarHeading();
    double getGunHeat();
    double getBattleFieldWidth();
    double getBattleFieldHeight();
    int getOthers();
    int getNumSentries();
    int getNumRounds();
    int getRoundNum();
    int getSentryBorderSize();
    double getGunCoolingRate();
    double getDistanceRemaining();
    double getBodyTurnRemaining();
    double getGunTurnRemaining();
    double getRadarTurnRemaining();
    void execute();
    void move(double distance);
    void turnBody(double radians);
    void turnGun(double radians);
    Bullet fire(double power);
    Bullet setFire(double power);
    void setBodyColor(Color color);
    void setGunColor(Color color);
    void setRadarColor(Color color);
    void setBulletColor(Color color);
    void setScanColor(Color color);
    void getCall();
    void setCall();
    Graphics2D getGraphics();
    void setDebugProperty(String key, String value);
    void rescan();
}
