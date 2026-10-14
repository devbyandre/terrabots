package robocode;

/** Base class of all Robocode events. */
public abstract class Event implements Comparable<Event>, java.io.Serializable {
    private long time;
    private Integer priority;

    public long getTime() { return time; }

    public void setTime(long time) { this.time = time; }

    public int getPriority() { return priority != null ? priority : defaultPriority(); }

    @Deprecated
    public void setPriority(int priority) { this.priority = priority; }

    @Override
    public int compareTo(Event e) {
        int byTime = Long.compare(time, e.time);
        return byTime != 0 ? byTime : Integer.compare(e.getPriority(), getPriority());
    }

    abstract int defaultPriority();

    abstract void dispatch(Robot r);
}
