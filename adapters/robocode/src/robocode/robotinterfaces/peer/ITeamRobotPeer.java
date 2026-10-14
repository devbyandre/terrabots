package robocode.robotinterfaces.peer;

import java.io.IOException;
import java.io.Serializable;
import java.util.List;

import robocode.MessageEvent;

public interface ITeamRobotPeer extends IAdvancedRobotPeer {
    String[] getTeammates();
    boolean isTeammate(String name);
    void broadcastMessage(Serializable message) throws IOException;
    void sendMessage(String name, Serializable message) throws IOException;
    List<MessageEvent> getMessageEvents();
}
