"""CommsMgr: range+LOS gated sends and the per-tick mailbox delivery model."""

from terrabots.comms import CommsMgr, MessageType
from terrabots.world_terrain import Cell, CreatureMoveProfile, TerrainType, VisibilityMgr, WorldGrid

PROFILE = CreatureMoveProfile(eye_height_offset=1.0, max_perception_range=15.0)


def make_comms() -> CommsMgr:
    """10x1 world with a tall rock at x=5 (blocks LOS between the two halves)."""
    world = WorldGrid(width=10, height=1)
    world.set(5, 0, Cell(terrain=TerrainType.ROCK, elevation=3.0))
    return CommsMgr(VisibilityMgr(world))


def send(comms: CommsMgr, recipient_id: int, recipient_pos: tuple[int, int],
         profile: CreatureMoveProfile = PROFILE, kind: str = "food_found") -> bool:
    return comms.send(
        sender_id=1, sender_pos=(0, 0), sender_profile=profile,
        recipient_id=recipient_id, recipient_pos=recipient_pos,
        message_type=MessageType.SIGNAL, payload={"kind": kind},
    )


def test_in_range_clear_los_is_accepted() -> None:
    assert send(make_comms(), 2, (2, 0)) is True


def test_blocked_by_tall_rock() -> None:
    assert send(make_comms(), 3, (9, 0)) is False


def test_beyond_perception_range_is_dropped() -> None:
    # Shout range is large, but LOS still needs the target within perception range.
    comms = CommsMgr(VisibilityMgr(WorldGrid(width=20, height=1)))
    short_sight = CreatureMoveProfile(max_perception_range=3.0)
    assert send(comms, 2, (10, 0), profile=short_sight) is False


def test_beyond_shout_range_is_dropped() -> None:
    comms = CommsMgr(VisibilityMgr(WorldGrid(width=20, height=1)))
    short_shout = CreatureMoveProfile(max_perception_range=15.0, max_shout_range=3.0)
    assert send(comms, 2, (10, 0), profile=short_shout) is False


def test_mailbox_empty_until_deliver() -> None:
    comms = make_comms()
    send(comms, 2, (2, 0))
    assert comms.get_inbox(2) == []
    comms.deliver()
    inbox = comms.get_inbox(2)
    assert len(inbox) == 1
    assert inbox[0].sender_id == 1
    assert inbox[0].payload == {"kind": "food_found"}


def test_dropped_message_never_arrives() -> None:
    comms = make_comms()
    send(comms, 3, (9, 0))
    comms.deliver()
    assert comms.get_inbox(3) == []


def test_clear_resets_mailboxes() -> None:
    comms = make_comms()
    send(comms, 2, (2, 0))
    comms.deliver()
    comms.clear()
    assert comms.get_inbox(2) == []
