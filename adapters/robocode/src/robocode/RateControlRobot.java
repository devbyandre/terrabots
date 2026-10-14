package robocode;

/** Robocode's RateControlRobot: speeds and turn rates instead of distances. */
public class RateControlRobot extends TeamRobot {
    public void setVelocityRate(double rate) { peer.velocityRate = rate; }
    public double getVelocityRate() { return peer.velocityRate != null ? peer.velocityRate : 0; }
    public void setTurnRate(double degrees) { peer.turnRate = degrees; }
    public void setTurnRateRadians(double radians) { peer.turnRate = Math.toDegrees(radians); }
    public double getTurnRate() { return peer.turnRate != null ? peer.turnRate : 0; }
    public double getTurnRateRadians() { return Math.toRadians(getTurnRate()); }
    public void setGunRotationRate(double degrees) { peer.gunRate = degrees; }
    public void setGunRotationRateRadians(double radians) { peer.gunRate = Math.toDegrees(radians); }
    public double getGunRotationRate() { return peer.gunRate != null ? peer.gunRate : 0; }
    public void setRadarRotationRate(double degrees) { peer.radarRate = degrees; }
    public void setRadarRotationRateRadians(double radians) { peer.radarRate = Math.toDegrees(radians); }
    public double getRadarRotationRate() { return peer.radarRate != null ? peer.radarRate : 0; }
}
