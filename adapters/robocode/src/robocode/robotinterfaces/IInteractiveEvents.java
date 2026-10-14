package robocode.robotinterfaces;

import java.awt.event.KeyEvent;
import java.awt.event.MouseEvent;
import java.awt.event.MouseWheelEvent;

/** Keyboard and mouse events (never sent: Terrabots battles have no keyboard). */
public interface IInteractiveEvents {
    void onKeyPressed(KeyEvent e);
    void onKeyReleased(KeyEvent e);
    void onKeyTyped(KeyEvent e);
    void onMouseClicked(MouseEvent e);
    void onMouseEntered(MouseEvent e);
    void onMouseExited(MouseEvent e);
    void onMousePressed(MouseEvent e);
    void onMouseReleased(MouseEvent e);
    void onMouseMoved(MouseEvent e);
    void onMouseDragged(MouseEvent e);
    void onMouseWheelMoved(MouseWheelEvent e);
}
