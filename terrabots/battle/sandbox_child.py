"""
The bot side of a sandboxed bot: runs inside the container (python -m
terrabots.battle.sandbox_child) and answers the engine's JSON lines on stdin.

    engine: {"t": "start", "mode": "battle" | "survival", "spec", "world", "seed"}
    bot:    {"t": "ready", "class", "droid"}       or {"t": "error", "msg"}
    engine: {"t": "round", ...} -> bot: {"t": "ok", ...}          (battle)
    engine: {"t": "birth", ...} -> bot: {"t": "ok"}               (survival)
    engine: {"t": "decide", "seq", "obs"} -> bot: {"t": "action", "seq", ...}
                                           or {"t": "decide_error", "seq", "msg"}
    engine: {"t": "death"} / {"t": "round_end", "won"} / {"t": "stop"}

Only this file talks to the engine. The bot's own prints go to stderr (and to
the console capture), never into the reply channel.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import traceback
from typing import Any


def main() -> None:
    # Keep the real stdout for replies; everything else written to fd 1 lands on stderr.
    replies = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    from terrabots.battle import wire
    from terrabots.battle.agent import BattleAgent
    from terrabots.battle.config import BattleConfig
    from terrabots.battle.observation import TerrainView
    from terrabots.battle.storage import BotStorage
    from terrabots.console import MAX_CHARS, MAX_LINES, capture
    from terrabots.world_terrain import MovementResolver

    def send(msg: dict[str, Any]) -> None:
        replies.write(json.dumps(msg) + "\n")

    start = json.loads(sys.stdin.readline())
    if start.get("seed") is not None:
        random.seed(start["seed"])
    world = wire.world_in(start["world"]) if start.get("world") else None   # battle bots only
    movement = MovementResolver(world) if world is not None else None
    try:
        import importlib

        module, _, name = start["spec"].partition(":")
        cls = getattr(importlib.import_module(module), name)
    except Exception:
        send({"t": "error", "msg": traceback.format_exc(limit=5)})
        return
    send({"t": "ready", "class": cls.__name__, "droid": bool(getattr(cls, "droid", False))})
    battle = start["mode"] == "battle"
    memory: dict[str, Any] = {}
    storage = BotStorage("/data", "bot", start.get("quota_kb", 200)) if battle else None
    agent = None

    for line in sys.stdin:
        msg = json.loads(line)
        kind = msg["t"]
        try:
            if kind == "round":
                agent = cls()
                agent.bot_id, agent.name, agent.memory = msg["bot_id"], msg["name"], memory
                agent.rules = BattleConfig.from_dict(msg["rules"])
                agent.storage = storage
                agent.team, agent.is_leader = msg["team"], msg["leader"]
                agent.teammates = {int(k): v for k, v in msg["teammates"].items()}
                agent.on_round_start(msg["round"], msg["rounds"])
                send({"t": "ok", "adj_gun": bool(agent.adjust_gun_for_body_turn),
                      "adj_radar": bool(agent.adjust_radar_for_gun_turn), "colors": dict(agent.colors)})
            elif kind == "birth":
                agent = cls()
                agent.agent_id, agent.pos, agent.energy = msg["agent_id"], tuple(msg["pos"]), msg["energy"]
                agent.on_birth()
                send({"t": "ok"})
            elif kind == "decide":
                assert agent is not None
                t0 = time.perf_counter()
                if battle:
                    obs = wire.battle_obs_in(msg["obs"])
                    obs.terrain = TerrainView(world, movement, agent.profile, obs.x, obs.y)
                    agent.draw.clear()
                    with capture(agent, msg.get("console", False)) as lines:
                        action = agent.decide(obs)
                    reply = {"action": wire.battle_action_out(action), "shapes": agent.draw.shapes,
                             "adj_gun": bool(agent.adjust_gun_for_body_turn),
                             "adj_radar": bool(agent.adjust_radar_for_gun_turn),
                             "outbox": [[to, data] for to, data in agent.take_outbox()]}
                else:
                    obs = wire.survival_obs_in(msg["obs"])
                    agent.pos, agent.energy = obs.pos, obs.energy
                    for m in obs.inbox:     # the engine calls on_message before decide, so do we
                        agent.on_message(m.sender_id, m.type.name, m.payload)
                    with capture(agent, msg.get("console", False)) as lines:
                        action = agent.decide(obs)
                    reply = {"action": wire.survival_action_out(action)}
                send({"t": "action", "seq": msg["seq"], "elapsed_ms": (time.perf_counter() - t0) * 1000,
                      "console": [line[:MAX_CHARS] for line in lines[:MAX_LINES]], **reply})
            elif kind == "death":
                if agent is not None:
                    agent.on_death()
            elif kind == "round_end":
                if agent is not None and isinstance(agent, BattleAgent):
                    agent.on_round_end(won=msg["won"])
            elif kind == "stop":
                return
        except Exception:
            if kind == "decide":
                send({"t": "decide_error", "seq": msg["seq"], "msg": traceback.format_exc(limit=5)})
            elif kind in ("round", "birth"):
                send({"t": "error", "msg": traceback.format_exc(limit=5)})
            else:
                traceback.print_exc()


if __name__ == "__main__":
    main()
