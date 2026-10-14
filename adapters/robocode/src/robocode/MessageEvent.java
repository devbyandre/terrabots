package robocode;

/** Robocode's MessageEvent (Terrabots adapter: written from the public API, not Robocode's source). */
public class MessageEvent extends Event {
    private final String sender;
    private final java.io.Serializable message;

    public MessageEvent(String sender, java.io.Serializable message) {
        this.sender = sender;
        this.message = message;
    }

    public String getSender() { return sender; }
    public java.io.Serializable getMessage() { return message; }

    @Override
    int defaultPriority() { return 75; }

    @Override
    void dispatch(Robot r) { if (r instanceof TeamRobot) ((TeamRobot) r).onMessageReceived(this); }
}
