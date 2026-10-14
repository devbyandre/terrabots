package robocode;

/** Part of Robocode's class chain: holds the link to the engine, and Robocode 1.0 names. */
public class _Robot {
    _Peer peer;

    @Deprecated public double getLife() { return peer.energy; }
    @Deprecated public int getBattleNum() { return 0; }
    @Deprecated public int getNumBattles() { return 1; }
    @Deprecated public String getGunImageName() { return null; }
    @Deprecated public String getRadarImageName() { return null; }
    @Deprecated public String getRobotImageName() { return null; }
    @Deprecated public void setGunImageName(String name) { }
    @Deprecated public void setRadarImageName(String name) { }
    @Deprecated public void setRobotImageName(String name) { }
}
