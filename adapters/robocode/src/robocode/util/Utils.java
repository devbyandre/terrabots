package robocode.util;

import java.util.Random;

/** Robocode's angle helpers. */
public final class Utils {
    private Utils() { }

    private static final double TWO_PI = 2 * Math.PI;
    private static final double NEAR = 1e-5;
    static Random random = new Random();

    public static double normalAbsoluteAngle(double a) {
        a %= TWO_PI;
        return a >= 0 ? a : a + TWO_PI;
    }

    public static double normalAbsoluteAngleDegrees(double a) {
        a %= 360;
        return a >= 0 ? a : a + 360;
    }

    public static double normalRelativeAngle(double a) {
        a %= TWO_PI;
        if (a >= Math.PI) return a - TWO_PI;
        return a < -Math.PI ? a + TWO_PI : a;
    }

    public static double normalRelativeAngleDegrees(double a) {
        a %= 360;
        if (a >= 180) return a - 360;
        return a < -180 ? a + 360 : a;
    }

    public static double normalNearAbsoluteAngle(double a) {
        a = normalAbsoluteAngle(a);
        return isNear(a, TWO_PI) ? 0 : a;
    }

    public static double normalNearAbsoluteAngleDegrees(double a) {
        a = normalAbsoluteAngleDegrees(a);
        return isNear(a, 360) ? 0 : a;
    }

    public static boolean isNear(double a, double b) { return Math.abs(a - b) < NEAR; }

    public static Random getRandom() { return random; }

    /** Used by the Terrabots host to make Utils.getRandom() repeatable per seed. */
    public static void setSeed(long seed) { random = new Random(seed); }
}
