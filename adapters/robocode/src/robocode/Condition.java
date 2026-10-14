package robocode;

/** A test for custom events (addCustomEvent) and waitFor(). */
public abstract class Condition {
    public String name;
    public int priority = 80;

    public Condition() { }

    public Condition(String name) { this.name = name; }

    public Condition(String name, int priority) { this.name = name; this.priority = priority; }

    public abstract boolean test();

    public String getName() { return name != null ? name : getClass().getName(); }

    public final int getPriority() { return priority; }

    public void setName(String name) { this.name = name; }

    public void setPriority(int priority) { this.priority = priority; }

    public void cleanup() { }
}
