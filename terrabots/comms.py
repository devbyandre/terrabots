"""
Inter-agent communication: range-limited and line-of-sight-gated message passing.

Design notes (assumptions made explicit):
- A message can only be received if the sender and receiver are within
  CreatureMoveProfile.max_perception_range of each other AND have line of sight,
  reusing VisibilityMgr directly. This means communication range is currently coupled
  to perception range -- if you later want comms to have a different range than vision
  (e.g. shouting further than you can see, or a species with poor sight but good
  hearing), add a separate max_comms_range field rather than overloading
  max_perception_range. Not built now because nothing in the current requirements asks
  for decoupling it, but flagging it as the obvious extension point.
- Payload is intentionally a free-form dict behind a typed envelope (MessageType +
  metadata), per your "extensible later, simple now" requirement. Start with whatever
  single signal type you need (e.g. MessageType.SIGNAL with payload={"kind": "danger"});
  add new MessageType values and payload shapes as problem-solving/strategy-alignment
  needs become concrete, without changing the envelope or delivery mechanism.
- Delivery model is a per-tick mailbox: messages sent during a tick are queued and only
  become readable after CommsMgr.deliver() runs, rather than being instantly readable
  by the receiver mid-tick. This avoids order-of-iteration bugs (agent A's message
  affecting agent B's decision within the same tick just because A was processed
  first) and mirrors the same-tick-consistency assumption the WorldGrid tick loop
  already uses for movement.
- No message history/persistence beyond the current tick's mailbox -- if you want
  agents to remember past messages, that's a memory/state concern that belongs in the
  agent/policy layer, not here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from terrabots.world_terrain import CreatureMoveProfile, VisibilityMgr


class MessageType(Enum):
    SIGNAL = auto()  # initial simple case: a typed flag, e.g. {"kind": "danger"}
    # Extend here as needs become concrete, e.g.:
    # POSITION_SHARE = auto()
    # STRATEGY_PROPOSAL = auto()


@dataclass
class Message:
    sender_id: int
    type: MessageType
    payload: dict[str, Any] = field(default_factory=dict)


class CommsMgr:
    """Range- and line-of-sight-gated message passing between agents, per tick.

    Usage per tick:
        comms.send(sender_id, sender_pos, sender_profile, target_id, target_pos, msg_type, payload)
        ... (repeat for all sends this tick) ...
        comms.deliver()
        inbox = comms.get_inbox(some_agent_id)   # messages that arrived this tick
        comms.clear()                             # reset for next tick
    """

    def __init__(self, visibility: VisibilityMgr):
        self._visibility = visibility
        self._pending: list[tuple[int, Message]] = []  # (recipient_id, message)
        self._mailboxes: dict[int, list[Message]] = defaultdict(list)

    def send(
        self,
        sender_id: int,
        sender_pos: tuple[int, int],
        sender_profile: CreatureMoveProfile,
        recipient_id: int,
        recipient_pos: tuple[int, int],
        message_type: MessageType,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """Attempt to send a message. Returns True if it will be delivered this tick.

        Gating: two independent checks.

        1. Shout range -- uses sender_profile.max_shout_range (separate from
           max_perception_range, which governs sight). A creature can shout further than
           it can see, or be constrained to shout less far. The squared-distance cull in
           VisibilityMgr still uses max_perception_range for sight; here we do our own
           shout-range check before calling LOS.
        2. Line of sight -- the message still requires an unobstructed sight-line within
           max_perception_range. The rationale: you can only shout to someone you could
           theoretically see (no shouting through mountains). If you want radio-style
           range-only comms with no LOS requirement, set cell elevations uniformly low
           so LOS is always clear, or override this method in a subclass.

        Returns True if the message will be delivered this tick; False if dropped.
        The caller can use this to decide whether to move closer or try another route.
        """
        dx = recipient_pos[0] - sender_pos[0]
        dy = recipient_pos[1] - sender_pos[1]
        squared_dist = dx * dx + dy * dy
        shout_range = sender_profile.max_shout_range
        if squared_dist > shout_range * shout_range:
            return False  # beyond shout range; no LOS check needed

        in_los = self._visibility.has_line_of_sight(
            sender_pos, recipient_pos, sender_profile
        )
        if not in_los:
            return False

        message = Message(sender_id=sender_id, type=message_type, payload=payload or {})
        self._pending.append((recipient_id, message))
        return True

    def deliver(self) -> None:
        """Move all messages sent this tick into recipient mailboxes.

        Until this is called, get_inbox() will not reflect messages sent via send()
        during the current tick -- this is the mechanism that enforces the
        same-tick-consistency assumption described in the module docstring.
        """
        for recipient_id, message in self._pending:
            self._mailboxes[recipient_id].append(message)
        self._pending.clear()

    def get_inbox(self, agent_id: int) -> list[Message]:
        """Messages delivered to this agent as of the last deliver() call."""
        return list(self._mailboxes.get(agent_id, []))

    def clear(self) -> None:
        """Empty all mailboxes. Call once per tick after agents have read their inbox."""
        self._mailboxes.clear()
