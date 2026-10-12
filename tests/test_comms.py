"""
Demonstrates CommsMgr: range+LOS gated sends, and the per-tick mailbox delivery model.

Run directly: python test_comms.py
"""

from terrabots.world_terrain import Cell, CreatureMoveProfile, TerrainType, VisibilityMgr, WorldGrid
from terrabots.comms import CommsMgr, MessageType


def main() -> None:
    # Reuse the same short-rock/tall-rock distinction from test_world_terrain.py,
    # since comms gating is built directly on VisibilityMgr.
    world = WorldGrid(width=10, height=1)
    world.set(5, 0, Cell(terrain=TerrainType.ROCK, elevation=3.0))  # tall: blocks
    visibility = VisibilityMgr(world)
    comms = CommsMgr(visibility)

    profile = CreatureMoveProfile(eye_height_offset=1.0, max_perception_range=15.0)

    # --- Scenario 1: in range, clear LOS -> delivered ---
    sent = comms.send(
        sender_id=1, sender_pos=(0, 0), sender_profile=profile,
        recipient_id=2, recipient_pos=(2, 0),
        message_type=MessageType.SIGNAL, payload={"kind": "food_found"},
    )
    print(f"[Scenario 1] Send within range, clear LOS: accepted={sent} (expected: True)")
    assert sent is True

    # --- Scenario 2: in range, but blocked by tall rock -> dropped ---
    sent_blocked = comms.send(
        sender_id=1, sender_pos=(0, 0), sender_profile=profile,
        recipient_id=3, recipient_pos=(9, 0),  # rock at x=5 sits between them
        message_type=MessageType.SIGNAL, payload={"kind": "danger"},
    )
    print(f"[Scenario 2] Send blocked by rock: accepted={sent_blocked} (expected: False)")
    assert sent_blocked is False

    # --- Scenario 3: clear LOS but beyond max_perception_range -> dropped ---
    short_range_profile = CreatureMoveProfile(max_perception_range=3.0)
    far_world = WorldGrid(width=20, height=1)  # no obstacles
    far_comms = CommsMgr(VisibilityMgr(far_world))
    sent_far = far_comms.send(
        sender_id=1, sender_pos=(0, 0), sender_profile=short_range_profile,
        recipient_id=2, recipient_pos=(10, 0),
        message_type=MessageType.SIGNAL, payload={"kind": "danger"},
    )
    print(f"[Scenario 3] Send beyond max_perception_range: accepted={sent_far} (expected: False)")
    assert sent_far is False

    # --- Scenario 4: mailbox is empty until deliver() is called ---
    inbox_before_deliver = comms.get_inbox(2)
    print(f"[Scenario 4] Inbox before deliver(): {inbox_before_deliver} (expected: [])")
    assert inbox_before_deliver == []

    comms.deliver()
    inbox_after_deliver = comms.get_inbox(2)
    print(f"[Scenario 5] Inbox after deliver(): "
          f"{[(m.sender_id, m.payload) for m in inbox_after_deliver]} "
          f"(expected: one message from sender 1)")
    assert len(inbox_after_deliver) == 1
    assert inbox_after_deliver[0].sender_id == 1
    assert inbox_after_deliver[0].payload == {"kind": "food_found"}

    # Agent 3 should have nothing -- their message was dropped by the rock in Scenario 2.
    inbox_agent_3 = comms.get_inbox(3)
    print(f"[Scenario 6] Agent 3 inbox (message was blocked): {inbox_agent_3} (expected: [])")
    assert inbox_agent_3 == []

    # --- Scenario 7: clear() resets mailboxes for the next tick ---
    comms.clear()
    inbox_after_clear = comms.get_inbox(2)
    print(f"[Scenario 7] Inbox after clear(): {inbox_after_clear} (expected: [])")
    assert inbox_after_clear == []

    print("\nAll scenarios passed.")


if __name__ == "__main__":
    main()


def test_scenarios() -> None:
    """pytest entry point: runs every scenario; each asserts internally."""
    main()
