package robocode;

/** Robocode's WinEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class WinEvent extends Event {


    public WinEvent() {

    }


    @Override
    int defaultPriority() { return 100; }

    @Override
    void dispatch(_Peer p) { if (p.basic != null) p.basic.onWin(this); }
}
