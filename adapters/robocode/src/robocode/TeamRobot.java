package robocode;

import java.io.IOException;
import java.io.Serializable;
import java.util.Map;
import java.util.Vector;

import robocode.robotinterfaces.ITeamEvents;
import robocode.robotinterfaces.ITeamRobot;

/** Robocode's TeamRobot: messages between teammates. */
public class TeamRobot extends AdvancedRobot implements ITeamEvents, ITeamRobot {
    @Override public final ITeamEvents getTeamEventListener() { return this; }
    public void broadcastMessage(Serializable message) throws IOException { peer.queueMessage(null, message); }

    public void sendMessage(String name, Serializable message) throws IOException {
        for (Map.Entry<Integer, String> e : peer.teammates.entrySet()) {
            if (e.getValue().equals(name)) peer.queueMessage(e.getKey(), message);
        }
    }

    public String[] getTeammates() {
        return peer.teammates.isEmpty() ? null : peer.teammates.values().toArray(new String[0]);
    }

    public boolean isTeammate(String name) { return peer.teammates.containsValue(name); }

    public Vector<MessageEvent> getMessageEvents() {
        Vector<MessageEvent> out = new Vector<>();
        for (Event e : peer.allEvents()) if (e instanceof MessageEvent) out.add((MessageEvent) e);
        return out;
    }

    @Override public void onMessageReceived(MessageEvent e) { }
}
