"""
Plain-JSON messages between the engine and a sandboxed bot (terrabots.battle.sandbox).

Why not pickle, like the process isolation? Unpickling runs code chosen by
whoever made the data, so a malicious bot could take over the engine with its
reply. JSON carries only data, and everything a bot sends back is checked here
before the engine uses it: types, finite numbers, sizes. Anything else raises
WireError and the turn is skipped (or the bot stopped).

Engine -> bot data (observations, the world, rules) is trusted, so it is only
converted, not checked.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import math
import re
from typing import Any

import numpy as np

from terrabots.battle.actions import BattleAction
from terrabots.battle.agent import MAX_MESSAGE_BYTES, MAX_MESSAGES_PER_TICK
from terrabots.battle.debug import MAX_SHAPES
from terrabots.battle.events import (
    BotDeath, BulletFired, BulletHit, BulletHitBullet, BulletMissed, HitBot, HitByBullet,
    HitWall, ScannedBot, TeamMessage,
)
from terrabots.battle.observation import BattleObservation
from terrabots.comms import Message, MessageType
from terrabots.console import MAX_CHARS, MAX_LINES
from terrabots.framework.actions import Action, MoveDirection, Shout
from terrabots.framework.observation import AgentPercept, Observation, ResourcePercept, TerrainPercept
from terrabots.world_terrain import Cell, TerrainType, WorldGrid

MAX_LINE_BYTES = 1 << 20          # one reply; longer and the bot is stopped
MAX_TEXT = 80
COLOR = re.compile(r"^[#a-zA-Z0-9(),.% -]{1,40}$")
COLOR_PARTS = ("body", "gun", "radar", "bullet", "scan")

_EVENTS = {"scanned_bots": ScannedBot, "hit_by_bullet": HitByBullet, "bullet_hit": BulletHit,
           "bullet_missed": BulletMissed, "bullet_fired": BulletFired,
           "bullet_hit_bullet": BulletHitBullet, "hit_wall": HitWall, "hit_bot": HitBot,
           "bot_death": BotDeath}


class WireError(ValueError):
    """A bot sent something that isn't a valid reply."""


# ---------------------------------------------------------------------------
# Engine -> bot (trusted)
# ---------------------------------------------------------------------------

def _messages_out(inbox: list[Message]) -> list[dict[str, Any]]:
    return [{"sender_id": m.sender_id, "type": m.type.name, "payload": m.payload} for m in inbox]


def _messages_in(raw: list[dict[str, Any]]) -> list[Message]:
    return [Message(m["sender_id"], MessageType[m["type"]], m["payload"]) for m in raw]


def battle_obs_out(obs: BattleObservation) -> dict[str, Any]:
    d = {f.name: getattr(obs, f.name) for f in dataclasses.fields(obs) if f.name not in ("terrain", "inbox")}
    for k in _EVENTS:
        d[k] = [dataclasses.asdict(e) for e in d[k]]
    d["team_messages"] = [dataclasses.asdict(m) for m in obs.team_messages]
    d["inbox"] = _messages_out(obs.inbox)
    return d


def battle_obs_in(d: dict[str, Any]) -> BattleObservation:
    d = dict(d)
    for k, cls in _EVENTS.items():
        d[k] = [cls(**e) for e in d[k]]
    d["team_messages"] = [TeamMessage(**m) for m in d["team_messages"]]
    d["inbox"] = _messages_in(d["inbox"])
    return BattleObservation(**d)


def survival_obs_out(obs: Observation) -> dict[str, Any]:
    return {
        "tick": obs.tick, "agent_id": obs.agent_id, "pos": list(obs.pos), "energy": obs.energy,
        "elevation": obs.elevation,
        "visible_agents": [[a.agent_id, list(a.pos), a.energy, a.elevation] for a in obs.visible_agents],
        "visible_resources": [[list(r.pos), r.amount, r.elevation] for r in obs.visible_resources],
        "visible_terrain": [[list(t.pos), t.terrain_name, t.elevation, t.water_depth] for t in obs.visible_terrain],
        "nearest_resource": list(obs.nearest_resource) if obs.nearest_resource else None,
        "inbox": _messages_out(obs.inbox),
    }


def survival_obs_in(d: dict[str, Any]) -> Observation:
    return Observation(
        tick=d["tick"], agent_id=d["agent_id"], pos=tuple(d["pos"]), energy=d["energy"],
        elevation=d["elevation"],
        visible_agents=[AgentPercept(i, tuple(p), e, z) for i, p, e, z in d["visible_agents"]],
        visible_resources=[ResourcePercept(tuple(p), a, z) for p, a, z in d["visible_resources"]],
        visible_terrain=[TerrainPercept(tuple(p), n, z, w) for p, n, z, w in d["visible_terrain"]],
        nearest_resource=tuple(d["nearest_resource"]) if d["nearest_resource"] else None,
        inbox=_messages_in(d["inbox"]),
    )


def world_out(world: WorldGrid) -> dict[str, Any]:
    w, h = world.width, world.height
    cells = [[world.get(x, y) for x in range(w)] for y in range(h)]
    pack = lambda a: base64.b64encode(np.asarray(a, dtype=np.float32).tobytes()).decode()  # noqa: E731
    return {"width": w, "height": h,
            "elevation": pack([[c.elevation for c in row] for row in cells]),
            "water": pack([[c.water_depth for c in row] for row in cells]),
            "terrain": "".join(c.terrain.name[0] for row in cells for c in row)}


def world_in(d: dict[str, Any]) -> WorldGrid:
    w, h = d["width"], d["height"]
    elev = np.frombuffer(base64.b64decode(d["elevation"]), dtype=np.float32).reshape(h, w)
    water = np.frombuffer(base64.b64decode(d["water"]), dtype=np.float32).reshape(h, w)
    kinds = {t.name[0]: t for t in TerrainType}
    world = WorldGrid(w, h)
    for y in range(h):
        for x in range(w):
            world.set(x, y, Cell(kinds[d["terrain"][y * w + x]], float(elev[y, x]), float(water[y, x])))
    return world


# ---------------------------------------------------------------------------
# Bot -> engine (untrusted: check everything)
# ---------------------------------------------------------------------------

def parse_line(line: str) -> dict[str, Any]:
    if len(line) > MAX_LINE_BYTES:
        raise WireError("reply too long")
    try:
        msg = json.loads(line)
    except ValueError as exc:
        raise WireError(f"not JSON: {exc}") from None
    if not isinstance(msg, dict):
        raise WireError("reply is not an object")
    return msg


def number(v: Any, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise WireError(f"{what}: expected a finite number")
    return float(v)


def integer(v: Any, what: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise WireError(f"{what}: expected an integer")
    return v


def flag(v: Any, what: str) -> bool:
    if not isinstance(v, bool):
        raise WireError(f"{what}: expected true or false")
    return v


def text(v: Any, what: str, limit: int) -> str:
    if not isinstance(v, str) or len(v) > limit:
        raise WireError(f"{what}: expected text of at most {limit} characters")
    return v


def plain_data(v: Any, what: str, limit: int = MAX_MESSAGE_BYTES) -> Any:
    """JSON-decoded data is plain by construction; only its size needs checking."""
    if len(json.dumps(v)) > limit:
        raise WireError(f"{what}: more than {limit} bytes")
    return v


def _shout(v: Any) -> Shout | None:
    if v is None:
        return None
    if not isinstance(v, dict):
        raise WireError("shout: expected an object")
    payload = v.get("payload", {})
    if not isinstance(payload, dict):
        raise WireError("shout.payload: expected an object")
    return Shout(integer(v.get("recipient_id"), "shout.recipient_id"), text(v.get("kind", ""), "shout.kind", 40),
                 plain_data(payload, "shout.payload"))


def shout_out(s: Shout | None) -> dict[str, Any] | None:
    return None if s is None else {"recipient_id": s.recipient_id, "kind": s.kind, "payload": s.payload}


def battle_action_out(a: BattleAction) -> dict[str, Any]:
    return {"velocity": a.velocity, "body_turn": a.body_turn, "gun_turn": a.gun_turn,
            "radar_turn": a.radar_turn, "fire": a.fire, "fire_heading": a.fire_heading,
            "shout": shout_out(a.shout), "scan": a.scan}


def battle_action_in(v: Any) -> BattleAction:
    if not isinstance(v, dict):
        raise WireError("action: expected an object")
    return BattleAction(**{k: number(v.get(k, 0.0), k) for k in ("velocity", "body_turn", "gun_turn", "radar_turn", "fire")},
                        fire_heading=None if v.get("fire_heading") is None else number(v["fire_heading"], "fire_heading"),
                        shout=_shout(v.get("shout")), scan=flag(v.get("scan", False), "scan"))


def survival_action_out(a: Action) -> dict[str, Any]:
    return {"move_toward": list(a.move_toward) if a.move_toward is not None else None,
            "move_direction": a.move_direction.name if a.move_direction is not None else None,
            "shout": shout_out(a.shout)}


def survival_action_in(v: Any) -> Action:
    if not isinstance(v, dict):
        raise WireError("action: expected an object")
    toward = v.get("move_toward")
    if toward is not None:
        if not (isinstance(toward, list) and len(toward) == 2):
            raise WireError("move_toward: expected [x, y]")
        toward = (integer(toward[0], "move_toward"), integer(toward[1], "move_toward"))
    direction = v.get("move_direction")
    if direction is not None:
        if direction not in MoveDirection.__members__:
            raise WireError("move_direction: unknown direction")
        direction = MoveDirection[direction]
    return Action(move_toward=toward, move_direction=direction, shout=_shout(v.get("shout")))


def shapes_in(v: Any) -> list[dict[str, Any]]:
    if not isinstance(v, list) or len(v) > MAX_SHAPES:
        raise WireError(f"drawings: expected at most {MAX_SHAPES} shapes")
    out = []
    for s in v:
        if not isinstance(s, dict):
            raise WireError("drawings: expected objects")
        kind = s.get("k")
        color = text(s.get("c", "#ffffff"), "drawing colour", 40)
        if not COLOR.match(color):
            raise WireError("drawing colour: not a colour")
        if kind == "line":
            out.append({"k": "line", **{f: number(s.get(f), f) for f in ("x0", "y0", "x1", "y1")}, "c": color})
        elif kind == "circle":
            out.append({"k": "circle", **{f: number(s.get(f), f) for f in ("x", "y", "r")},
                        "c": color, "f": flag(s.get("f", False), "fill")})
        elif kind == "text":
            out.append({"k": "text", "x": number(s.get("x"), "x"), "y": number(s.get("y"), "y"),
                        "t": text(s.get("t", ""), "drawing text", MAX_TEXT), "c": color})
        else:
            raise WireError("drawings: unknown shape")
    return out


def console_in(v: Any) -> list[str]:
    if not isinstance(v, list) or len(v) > MAX_LINES:
        raise WireError(f"console: at most {MAX_LINES} lines")
    return [text(line, "console line", MAX_CHARS) for line in v]


def colors_in(v: Any) -> dict[str, str]:
    if not isinstance(v, dict):
        raise WireError("colors: expected an object")
    out = {}
    for part, c in v.items():
        if part not in COLOR_PARTS or not isinstance(c, str) or not COLOR.match(c):
            raise WireError(f"colors: bad entry {part!r}")
        out[part] = c
    return out


def outbox_in(v: Any) -> list[tuple[int | None, Any]]:
    if not isinstance(v, list) or len(v) > MAX_MESSAGES_PER_TICK:
        raise WireError(f"messages: at most {MAX_MESSAGES_PER_TICK} per tick")
    out = []
    for m in v:
        if not (isinstance(m, list) and len(m) == 2):
            raise WireError("messages: expected [recipient, data] pairs")
        to = None if m[0] is None else integer(m[0], "message recipient")
        out.append((to, plain_data(m[1], "message")))
    return out
