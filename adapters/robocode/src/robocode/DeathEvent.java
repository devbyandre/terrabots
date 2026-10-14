package robocode;

/** Robocode's DeathEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class DeathEvent extends Event {


    public DeathEvent() {

    }


    @Override
    int defaultPriority() { return -1; }

    @Override
    void dispatch(Robot r) { r.onDeath(this); }
}
