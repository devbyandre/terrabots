package robocode;

public class GunTurnCompleteCondition extends Condition {
    private final AdvancedRobot robot;

    public GunTurnCompleteCondition(AdvancedRobot robot) { super("GunTurnCompleteCondition"); this.robot = robot; }

    public GunTurnCompleteCondition(AdvancedRobot robot, int priority) { super("GunTurnCompleteCondition", priority); this.robot = robot; }

    @Override
    public boolean test() { return robot.getGunTurnRemaining() == 0; }
}
