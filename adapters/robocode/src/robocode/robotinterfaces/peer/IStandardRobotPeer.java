package robocode.robotinterfaces.peer;

public interface IStandardRobotPeer extends IBasicRobotPeer {
    void stop(boolean overwrite);
    void resume();
    void turnRadar(double radians);
    void setAdjustGunForBodyTurn(boolean independent);
    void setAdjustRadarForGunTurn(boolean independent);
    void setAdjustRadarForBodyTurn(boolean independent);
}
