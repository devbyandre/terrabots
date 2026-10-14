package robocode;

public class RadarTurnCompleteCondition extends Condition {
    private final AdvancedRobot robot;

    public RadarTurnCompleteCondition(AdvancedRobot robot) { super("RadarTurnCompleteCondition"); this.robot = robot; }

    public RadarTurnCompleteCondition(AdvancedRobot robot, int priority) { super("RadarTurnCompleteCondition", priority); this.robot = robot; }

    @Override
    public boolean test() { return robot.getRadarTurnRemaining() == 0; }
}
