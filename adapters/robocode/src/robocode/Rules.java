package robocode;

/** Robocode's game rules (pixels, degrees), as published on RoboWiki. */
public final class Rules {
    private Rules() { }

    public static final double ACCELERATION = 1, DECELERATION = 2, MAX_VELOCITY = 8;
    public static final double RADAR_SCAN_RADIUS = 1200;
    public static final double MIN_BULLET_POWER = 0.1, MAX_BULLET_POWER = 3;
    public static final double MAX_TURN_RATE = 10, GUN_TURN_RATE = 20, RADAR_TURN_RATE = 45;
    public static final double MAX_TURN_RATE_RADIANS = Math.toRadians(MAX_TURN_RATE);
    public static final double GUN_TURN_RATE_RADIANS = Math.toRadians(GUN_TURN_RATE);
    public static final double RADAR_TURN_RATE_RADIANS = Math.toRadians(RADAR_TURN_RATE);
    public static final double ROBOT_HIT_DAMAGE = 0.6, ROBOT_HIT_BONUS = 1.2;

    public static double getTurnRate(double velocity) { return MAX_TURN_RATE - 0.75 * Math.abs(velocity); }
    public static double getTurnRateRadians(double velocity) { return Math.toRadians(getTurnRate(velocity)); }
    public static double getWallHitDamage(double velocity) { return Math.max(Math.abs(velocity) / 2 - 1, 0); }
    public static double getBulletDamage(double power) { return 4 * power + Math.max(0, 2 * (power - 1)); }
    public static double getBulletHitBonus(double power) { return 3 * power; }
    public static double getBulletSpeed(double power) {
        return 20 - 3 * Math.max(MIN_BULLET_POWER, Math.min(MAX_BULLET_POWER, power));
    }
    public static double getGunHeat(double power) { return 1 + power / 5; }
}
