"""
Battle server: serves the viewer and runs the battles (and survival runs) the
browser asks for.

    http://<host>:<port>/      -> battle.html (setup screen, battle view, results)
    ws://<host>:<port>/ws      -> bidirectional JSON, see docs/arena-spec.md §10

Unlike the survival ViewerServer, viewers control the battle (start, pause, step,
speed, stop). There is one battle at a time; every connected viewer sees it and
can control it.

Client -> server: list_bots, start_battle {config, bots}, parse_toml {text},
                  start_survival {config, agents},
                  pause, resume, step, set_speed {tick_delay_ms}, set_pov {id}, stop_battle
Server -> client: hello {defaults, bots, survival}, bot_list, toml_parsed, error,
                  round_start {world, ...}, tick, round_end, battle_end, stopped,
                  survival_start {world, agents, config}, survival_tick, survival_end
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import tomllib
from http import HTTPStatus
from pathlib import Path
from typing import Any

import numpy as np
from websockets.asyncio.server import ServerConnection, serve
from websockets.http11 import Request, Response

from terrabots.battle.config import BattleConfigError, BattleFile
from terrabots.battle.discovery import discover_bots
from terrabots.battle.runner import BattleRunner
from terrabots.framework.agent import Agent
from terrabots.survival_session import SurvivalSession, SurvivalSettings, SurvivalSettingsError
from terrabots.world_terrain import TerrainType, WorldGrid

logger = logging.getLogger(__name__)

BATTLE_HTML = Path(__file__).with_name("battle.html")
TERRAIN_CODES = {TerrainType.PLAIN: 0, TerrainType.ROCK: 1, TerrainType.WATER: 2, TerrainType.STAIRS: 3}
ROUND_END_PAUSE_S = 1.5   # let viewers see who won before the next round


def world_payload(world: WorldGrid) -> dict[str, Any]:
    """Terrain as flat base64 arrays, index = y * width + x (one JSON dict per cell
    doesn't scale past ~64x64)."""
    w, h = world.width, world.height
    terrain = np.zeros((h, w), dtype=np.uint8)
    water = np.zeros((h, w), dtype=np.float32)
    for x in range(w):
        for y in range(h):
            cell = world.get(x, y)
            terrain[y, x] = TERRAIN_CODES[cell.terrain]
            water[y, x] = cell.water_depth
    elevation = world.elevation_map.T.astype(np.float32)  # (x, y) -> row-major by y

    def b64(a: np.ndarray) -> str:
        return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")

    return {"width": w, "height": h, "elevation": b64(elevation),
            "terrain": b64(terrain), "water_depth": b64(water),
            "terrain_codes": {t.name: c for t, c in TERRAIN_CODES.items()}}


class BattleServer:
    def __init__(self, defaults: BattleFile, extra_specs: list[str] | None = None,
                 extra_agents: list[str] | None = None,
                 host: str = "localhost", port: int = 8765,
                 results_dir: str = "results", data_dir: str | None = "bot_data",
                 time_budget_ms: float | None | str = "config",
                 autostart: bool = False) -> None:
        self.defaults = defaults
        self.extra_specs = list(extra_specs or []) + [b.spec for b in defaults.bots]
        self.extra_agents = list(extra_agents or [])
        self.host, self.port = host, port
        self.results_dir = results_dir
        self.data_dir = data_dir
        self.time_budget_ms = time_budget_ms
        self.autostart = autostart

        self._connections: set[ServerConnection] = set()
        self._runner: BattleRunner | None = None
        self._task: asyncio.Task | None = None
        self._paused = False
        self._step_requested = asyncio.Event()
        self._tick_delay_ms = defaults.config.tick_delay_ms
        self._last_round_start: str | None = None
        self._last_frame: str | None = None
        self._pov: int | None = None
        self._survival: SurvivalSession | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def serve_forever(self) -> None:
        async with serve(self._handler, self.host, self.port,
                         process_request=self._process_request, max_size=2**22):
            shown = "localhost" if self.host in ("0.0.0.0", "::") else self.host  # all interfaces
            print(f"  Battle viewer: http://{shown}:{self.port}/")
            if self.autostart:
                await self._start(self.defaults.config.to_dict(),
                                  [{"spec": b.spec, "count": b.count} for b in self.defaults.bots])
            await asyncio.Future()  # run until cancelled (Ctrl+C)

    def _process_request(self, connection: ServerConnection, request: Request) -> Response | None:
        if request.path.startswith("/ws"):
            return None
        if request.path not in ("/", "/index.html", "/battle.html"):
            return connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")
        response = connection.respond(HTTPStatus.OK, BATTLE_HTML.read_text(encoding="utf-8"))
        del response.headers["Content-Type"]
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        return response

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def _handler(self, ws: ServerConnection) -> None:
        self._connections.add(ws)
        try:
            await ws.send(json.dumps({
                "type": "hello",
                "defaults": {"config": self.defaults.config.to_dict(),
                             "bots": [{"spec": b.spec, "count": b.count} for b in self.defaults.bots]},
                "bots": [b.to_dict() for b in discover_bots(self.extra_specs)],
                "survival": {"defaults": SurvivalSettings().to_dict(),
                             "agents": [b.to_dict() for b in
                                        discover_bots(self.extra_agents, base=Agent)]},
                "running": self._task is not None and not self._task.done(),
                "paused": self._paused,
                "tick_delay_ms": self._tick_delay_ms,
            }))
            if self._task is not None and not self._task.done():
                for cached in (self._last_round_start, self._last_frame):
                    if cached:
                        await ws.send(cached)
            async for raw in ws:
                try:
                    await self._on_message(ws, json.loads(raw))
                except (ValueError, KeyError, TypeError) as exc:
                    await ws.send(json.dumps({"type": "error", "message": str(exc)}))
        finally:
            self._connections.discard(ws)

    async def _on_message(self, ws: ServerConnection, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "list_bots":
            bots = discover_bots(self.extra_specs)
            await ws.send(json.dumps({"type": "bot_list", "bots": [b.to_dict() for b in bots]}))
        elif kind == "start_battle":
            await self._start(msg.get("config", {}), msg.get("bots", []))
        elif kind == "start_survival":
            await self._start_survival(msg.get("config", {}), msg.get("agents", []))
        elif kind == "parse_toml":
            try:
                bf = BattleFile.from_dict(tomllib.loads(msg["text"]))
            except (tomllib.TOMLDecodeError, BattleConfigError) as exc:
                raise ValueError(f"TOML: {exc}") from exc
            await ws.send(json.dumps({"type": "toml_parsed", "config": bf.config.to_dict(),
                                      "bots": [{"spec": b.spec, "count": b.count} for b in bf.bots]}))
        elif kind == "pause":
            self._paused = True
            await self._broadcast({"type": "paused", "paused": True})
        elif kind == "resume":
            self._paused = False
            self._step_requested.set()
            await self._broadcast({"type": "paused", "paused": False})
        elif kind == "step":
            self._paused = True
            self._step_requested.set()
        elif kind == "set_pov":
            # Fog of war: whose view survival frames should include (None = off).
            self._pov = msg.get("id")
            if self._survival is not None:
                self._survival.pov = self._pov
        elif kind == "set_speed":
            self._tick_delay_ms = max(0, min(5000, int(msg["tick_delay_ms"])))
        elif kind == "stop_battle":
            await self._stop()
            await self._broadcast({"type": "stopped"})
        else:
            raise ValueError(f"unknown message type {kind!r}")

    async def _start(self, config: dict[str, Any], bots: list[dict[str, Any]]) -> None:
        bots = [b for b in bots if int(b.get("count", 0)) > 0]
        try:
            bf = BattleFile.from_dict({**config, "bots": bots})
            # Starting bot processes takes a moment; keep the event loop responsive.
            runner = await asyncio.to_thread(BattleRunner, bf.config, bf.bots,
                                             time_budget_ms=self.time_budget_ms, data_dir=self.data_dir)
        except (BattleConfigError, ValueError, ImportError, AttributeError, RuntimeError) as exc:
            await self._broadcast({"type": "error", "message": str(exc)})
            return
        await self._stop()
        self._runner = runner
        self._paused = False
        self._tick_delay_ms = bf.config.tick_delay_ms
        self._task = asyncio.create_task(self._run(runner, bf))

    async def _start_survival(self, config: dict[str, Any], agents: list[dict[str, Any]]) -> None:
        try:
            settings = SurvivalSettings.from_dict(config)
            entries = []
            for a in agents:
                count = int(a.get("count", 0))
                if count > 0:
                    cls = _load_class(str(a["spec"]))
                    if not (isinstance(cls, type) and issubclass(cls, Agent)):
                        raise ValueError(f"{a['spec']} is not a survival Agent")
                    entries.append((cls, count))
            session = await asyncio.to_thread(SurvivalSession, settings, entries)
        except (SurvivalSettingsError, ValueError, ImportError, AttributeError, RuntimeError) as exc:
            await self._broadcast({"type": "error", "message": str(exc)})
            return
        await self._stop()
        self._paused = False
        self._tick_delay_ms = settings.tick_delay_ms
        session.pov = self._pov
        self._survival = session
        self._task = asyncio.create_task(self._run_survival(session, agents))

    async def _stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._survival = None
        self._last_round_start = self._last_frame = None

    async def _broadcast(self, msg: dict[str, Any] | str) -> None:
        payload = msg if isinstance(msg, str) else json.dumps(msg)
        for ws in list(self._connections):
            try:
                await ws.send(payload)
            except Exception:  # closed mid-send; the handler's finally removes it
                self._connections.discard(ws)

    # ------------------------------------------------------------------
    # Loops
    # ------------------------------------------------------------------

    async def _pace(self) -> None:
        """Wait while paused (a step request lets one tick through)."""
        if self._paused:
            self._step_requested.clear()
            await self._step_requested.wait()

    async def _after_tick(self) -> None:
        if self._tick_delay_ms > 0 and not self._paused:
            await asyncio.sleep(self._tick_delay_ms / 1000)

    async def _run_survival(self, session: SurvivalSession, agents: list[dict[str, Any]]) -> None:
        try:
            self._last_round_start = json.dumps({
                "type": "survival_start", "world": world_payload(session.world),
                "agents": session.agents_info(), "config": session.settings.to_dict()})
            await self._broadcast(self._last_round_start)
            while not session.over:
                await self._pace()
                frame = await asyncio.to_thread(session.step)
                self._last_frame = json.dumps(frame)
                await self._broadcast(self._last_frame)
                await self._after_tick()
            await self._broadcast({"type": "survival_end", "tick": session.tick,
                                   "results": session.results(), "config": session.settings.to_dict(),
                                   "agents": agents})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Survival run crashed")
            await self._broadcast({"type": "error", "message": f"Survival run crashed: {exc}"})

    async def _run(self, runner: BattleRunner, bf: BattleFile) -> None:
        world = world_payload(runner.world)
        try:
            while not runner.done:
                arena = await asyncio.to_thread(runner.start_round)
                self._last_round_start = json.dumps({
                    "type": "round_start", "round": runner.round, "rounds": bf.config.rounds,
                    "world": world, "config": bf.config.to_dict(),
                    "bots": [{"id": bid, "name": name, "class": cls.__name__,
                              "colors": dict(arena.slots[bid].agent.colors),
                              "view": arena.slots[bid].agent.profile.max_perception_range}
                             for bid, (cls, name) in enumerate(runner.names)],
                })
                await self._broadcast(self._last_round_start)
                await self._broadcast(arena.frame())
                while not arena.over:
                    await self._pace()
                    frame = await asyncio.to_thread(runner.step)
                    self._last_frame = json.dumps(frame)
                    await self._broadcast(self._last_frame)
                    await self._after_tick()
                ranking = runner.end_round()
                await self._broadcast({"type": "round_end", "round": runner.round,
                                       "rounds": bf.config.rounds, "ranking": ranking,
                                       "survivors": len(arena.standing())})
                if not runner.done:
                    await asyncio.sleep(ROUND_END_PAUSE_S)
            results = runner.results()
            path = await asyncio.to_thread(results.save, self.results_dir)
            print(f"  Battle finished, results saved to {path}")
            print(results.table())
            await self._broadcast({"type": "battle_end", "results": results.rows,
                                   "rounds": results.rounds, "saved_to": str(path),
                                   "config": bf.config.to_dict(),
                                   "bots": [{"spec": b.spec, "count": b.count} for b in bf.bots]})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Battle crashed")
            await self._broadcast({"type": "error", "message": f"Battle crashed: {exc}"})
        finally:
            runner.close()


def _load_class(spec: str) -> type:
    import importlib

    module_name, _, class_name = spec.partition(":")
    if not class_name:
        raise ValueError(f"{spec!r}: expected 'module:ClassName'")
    return getattr(importlib.import_module(module_name), class_name)
