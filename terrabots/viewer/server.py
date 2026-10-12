"""
Viewer server: serves the Three.js page over HTTP and streams simulation state
over a WebSocket, both on the same port.

    http://<host>:<port>/      -> index.html (the viewer)
    ws://<host>:<port>/ws      -> JSON stream: one "world_state", then "tick" messages

Usage (normally via `terrabots-run`, see terrabots/run.py):

    server = ViewerServer(sim, host="localhost", port=8765)
    async with server:
        await server.run_simulation(ticks=1000, tick_delay=0.05)

Design notes:
- Read-only broadcast: viewers cannot influence the simulation.
- The simulation step runs in a worker thread (asyncio.to_thread) so a slow tick
  does not stall the event loop; broadcasting happens back on the loop after each
  step. No cross-thread callbacks are involved.
- If no viewer is connected, ticks are not buffered -- a late viewer joins live.
- Requires websockets >= 13 (new asyncio implementation, process_request API).
"""

from __future__ import annotations

import asyncio
import json
import logging
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.http11 import Request, Response

if TYPE_CHECKING:
    from terrabots.framework.simulation import Simulation, TickSnapshot

logger = logging.getLogger(__name__)

INDEX_HTML = Path(__file__).with_name("index.html")


class ViewerServer:
    """HTTP + WebSocket server broadcasting simulation snapshots."""

    def __init__(self, sim: "Simulation", host: str = "localhost", port: int = 8765) -> None:
        self.sim = sim
        self.host = host
        self.port = port
        self._connections: set[ServerConnection] = set()
        self._world_state_json = json.dumps({"type": "world_state", **sim.world_state()})
        self._server: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ViewerServer":
        self._server = await serve(
            self._handler, self.host, self.port, process_request=self._process_request
        )
        shown = "localhost" if self.host in ("0.0.0.0", "::") else self.host  # all interfaces
        print(f"  Viewer: http://{shown}:{self.port}/")
        return self

    async def __aexit__(self, *_: Any) -> None:
        self._server.close()
        await self._server.wait_closed()

    # ------------------------------------------------------------------
    # HTTP: serve index.html for any non-/ws path
    # ------------------------------------------------------------------

    def _process_request(self, connection: ServerConnection, request: Request) -> Response | None:
        if request.path.startswith("/ws"):
            return None  # continue with the WebSocket handshake
        if request.path not in ("/", "/index.html"):
            return connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")
        response = connection.respond(HTTPStatus.OK, INDEX_HTML.read_text(encoding="utf-8"))
        del response.headers["Content-Type"]
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        return response

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    async def _handler(self, ws: ServerConnection) -> None:
        self._connections.add(ws)
        logger.debug("Viewer connected (%d total)", len(self._connections))
        try:
            await ws.send(self._world_state_json)
            await ws.wait_closed()
        finally:
            self._connections.discard(ws)

    async def broadcast(self, snap: "TickSnapshot") -> None:
        if not self._connections:
            return
        payload = json.dumps({
            "type": "tick",
            "tick": snap.tick,
            "agents": snap.agents,
            "resources": snap.resources,
            "n_alive": snap.n_alive,
            "n_messages_sent": snap.n_messages_sent,
        })
        for ws in list(self._connections):
            try:
                await ws.send(payload)
            except Exception:  # closed mid-send; handler's finally removes it
                self._connections.discard(ws)

    # ------------------------------------------------------------------
    # Simulation driver
    # ------------------------------------------------------------------

    async def run_simulation(self, ticks: int, tick_delay: float = 0.05, verbose: bool = True) -> None:
        """Step the simulation, broadcasting each tick. tick_delay paces playback."""
        for _ in range(ticks):
            snap = await asyncio.to_thread(self.sim.step)
            await self.broadcast(snap)
            if verbose and snap.tick % 50 == 0:
                print(f"tick {snap.tick:4d} | alive={snap.n_alive} | "
                      f"resources={len(snap.resources)} | msgs={snap.n_messages_sent}")
            if snap.n_alive == 0:
                if verbose:
                    print(f"All agents dead at tick {snap.tick}. Stopping.")
                break
            if tick_delay > 0:
                await asyncio.sleep(tick_delay)
