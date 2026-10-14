package robocode;

public class TurnCompleteCondition extends Condition {
    private final AdvancedRobot robot;

    public TurnCompleteCondition(AdvancedRobot robot) { super("TurnCompleteCondition"); this.robot = robot; }

    public TurnCompleteCondition(AdvancedRobot robot, int priority) { super("TurnCompleteCondition", priority); this.robot = robot; }

    @Override
    public boolean test() { return robot.getTurnRemaining() == 0; }
}
