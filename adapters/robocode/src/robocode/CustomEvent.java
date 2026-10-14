package robocode;

/** Fired when a Condition added with addCustomEvent() is true. */
public class CustomEvent extends Event {
    private final Condition condition;

    public CustomEvent(Condition condition) { this.condition = condition; }

    public Condition getCondition() { return condition; }

    @Override
    int defaultPriority() { return condition.getPriority(); }

    @Override
    void dispatch(Robot r) { if (r instanceof AdvancedRobot) ((AdvancedRobot) r).onCustomEvent(this); }
}
