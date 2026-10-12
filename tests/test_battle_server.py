"""Battle CLI, bot discovery, terrain payload, and a WebSocket round trip."""

import asyncio
import base64
import json

import numpy as np

from terrabots.battle.cli import main as battle_main
from terrabots.battle.config import BattleFile
from terrabots.battle.discovery import discover_bots
from terrabots.viewer.battle_server import BattleServer, world_payload
from terrabots.world_terrain import Cell, TerrainType, WorldGrid


def test_discovery_finds_builtin_demo_bots() -> None:
    specs = {b.spec for b in discover_bots()}
    assert "terrabots.agents.tracker:Tracker" in specs
    assert "terrabots.agents.sitting_duck:SittingDuck" in specs


def test_world_payload_is_row_major_by_y() -> None:
    world = WorldGrid(4, 3)
    world.set(3, 1, Cell(TerrainType.ROCK, elevation=7.0))
    p = world_payload(world)
    elev = np.frombuffer(base64.b64decode(p["elevation"]), dtype=np.float32)
    codes = np.frombuffer(base64.b64decode(p["terrain"]), dtype=np.uint8)
    assert elev[1 * 4 + 3] == 7.0
    assert codes[1 * 4 + 3] == p["terrain_codes"]["ROCK"]


def test_cli_headless_saves_results(tmp_path, capsys) -> None:
    battle_main(["battles/example.toml", "--headless", "--rounds", "1", "--seed", "2",
                 "--results-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "rank" in out and "Saved" in out
    saved = list(tmp_path.glob("*.json"))
    assert len(saved) == 1
    assert len(json.loads(saved[0].read_text())["results"]) == 6


def test_websocket_battle_round_trip() -> None:
    from websockets.asyncio.client import connect

    async def scenario() -> list[str]:
        bf = BattleFile.from_dict({"rounds": 1, "max_ticks_per_round": 30, "tick_delay_ms": 0,
                                   "terrain": "flat", "seed": 1})
        server = BattleServer(bf, port=8799, results_dir="/tmp/terrabots-test-results",
                              time_budget_ms=None)
        task = asyncio.create_task(server.serve_forever())
        await asyncio.sleep(0.3)
        seen: list[str] = []
        try:
            async with connect("ws://localhost:8799/ws") as ws:
                hello = json.loads(await ws.recv())
                assert hello["type"] == "hello" and hello["bots"]
                await ws.send(json.dumps({"type": "start_battle", "config": bf.config.to_dict(),
                                          "bots": [{"spec": "terrabots.agents.spin_bot:SpinBot", "count": 2}]}))
                while "battle_end" not in seen:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    seen.append(msg["type"])
        finally:
            task.cancel()
        return seen

    seen = asyncio.run(scenario())
    assert seen[0] == "round_start"
    assert "tick" in seen and "round_end" in seen and seen[-1] == "battle_end"


def test_websocket_survival_round_trip() -> None:
    from websockets.asyncio.client import connect

    async def scenario() -> tuple[list[str], dict]:
        server = BattleServer(BattleFile.from_dict({}), port=8798, results_dir="/tmp/terrabots-test-results")
        task = asyncio.create_task(server.serve_forever())
        await asyncio.sleep(0.3)
        seen: list[str] = []
        end: dict = {}
        try:
            async with connect("ws://localhost:8798/ws") as ws:
                hello = json.loads(await ws.recv())
                specs = {a["spec"] for a in hello["survival"]["agents"]}
                assert "terrabots.agents.grazer:Grazer" in specs
                await ws.send(json.dumps({
                    "type": "start_survival",
                    "config": {**hello["survival"]["defaults"], "size": 24, "max_ticks": 30,
                               "tick_delay_ms": 0, "seed": 1},
                    "agents": [{"spec": "terrabots.agents.grazer:Grazer", "count": 3}]}))
                while "survival_end" not in seen:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    seen.append(msg["type"])
                    if msg["type"] == "survival_end":
                        end = msg
        finally:
            task.cancel()
        return seen, end

    seen, end = asyncio.run(scenario())
    assert seen[0] == "survival_start" and "survival_tick" in seen
    assert end["tick"] == 30 and end["results"][0]["class"] == "Grazer"


def test_survival_settings_validation() -> None:
    import pytest

    from terrabots.survival_session import SurvivalSettings, SurvivalSettingsError

    with pytest.raises(SurvivalSettingsError, match="size"):
        SurvivalSettings(size=4)
    with pytest.raises(SurvivalSettingsError, match="foo"):
        SurvivalSettings.from_dict({"foo": 1})
