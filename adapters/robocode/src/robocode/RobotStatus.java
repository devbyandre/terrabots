package robocode;

/** A snapshot of your robot (StatusEvent). */
public final class RobotStatus implements java.io.Serializable {
    private final double x, y, energy, heading, gunHeading, radarHeading, velocity, gunHeat;
    private final double distance, turn, gunTurn, radarTurn;
    private final int others, roundNum, numRounds;
    private final long time;

    RobotStatus(double x, double y, double energy, double heading, double gunHeading, double radarHeading,
                double velocity, double gunHeat, double distance, double turn, double gunTurn, double radarTurn,
                int others, int roundNum, int numRounds, long time) {
        this.x = x; this.y = y; this.energy = energy; this.heading = heading; this.gunHeading = gunHeading;
        this.radarHeading = radarHeading; this.velocity = velocity; this.gunHeat = gunHeat; this.distance = distance;
        this.turn = turn; this.gunTurn = gunTurn; this.radarTurn = radarTurn; this.others = others;
        this.roundNum = roundNum; this.numRounds = numRounds; this.time = time;
    }

    public double getX() { return x; }
    public double getY() { return y; }
    public double getEnergy() { return energy; }
    public double getHeading() { return heading; }
    public double getHeadingRadians() { return Math.toRadians(heading); }
    public double getGunHeading() { return gunHeading; }
    public double getGunHeadingRadians() { return Math.toRadians(gunHeading); }
    public double getRadarHeading() { return radarHeading; }
    public double getRadarHeadingRadians() { return Math.toRadians(radarHeading); }
    public double getVelocity() { return velocity; }
    public double getGunHeat() { return gunHeat; }
    public double getDistanceRemaining() { return distance; }
    public double getTurnRemaining() { return turn; }
    public double getTurnRemainingRadians() { return Math.toRadians(turn); }
    public double getGunTurnRemaining() { return gunTurn; }
    public double getGunTurnRemainingRadians() { return Math.toRadians(gunTurn); }
    public double getRadarTurnRemaining() { return radarTurn; }
    public double getRadarTurnRemainingRadians() { return Math.toRadians(radarTurn); }
    public int getOthers() { return others; }
    public int getNumSentries() { return 0; }
    public int getRoundNum() { return roundNum; }
    public int getNumRounds() { return numRounds; }
    public long getTime() { return time; }
}
