package robocode;

public class MoveCompleteCondition extends Condition {
    private final AdvancedRobot robot;

    public MoveCompleteCondition(AdvancedRobot robot) { super("MoveCompleteCondition"); this.robot = robot; }

    public MoveCompleteCondition(AdvancedRobot robot, int priority) { super("MoveCompleteCondition", priority); this.robot = robot; }

    @Override
    public boolean test() { return robot.getDistanceRemaining() == 0; }
}
