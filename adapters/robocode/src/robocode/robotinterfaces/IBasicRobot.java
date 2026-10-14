package robocode.robotinterfaces;

import java.io.PrintStream;

import robocode.robotinterfaces.peer.IBasicRobotPeer;

/** Robocode's robot interface family: what the engine calls on a robot. */
public interface IBasicRobot {
    Runnable getRobotRunnable();
    IBasicEvents getBasicEventListener();
    void setPeer(IBasicRobotPeer peer);
    void setOut(PrintStream out);
}
