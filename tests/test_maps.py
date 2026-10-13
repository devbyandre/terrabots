"""Map files: built-in maps, round trip, validation, playability check, use in battles."""

import json

import pytest

from terrabots import maps
from terrabots.battle import BattleConfig, BattleRunner
from terrabots.battle.config import BattleConfigError
from terrabots.survival_session import SurvivalSession, SurvivalSettings, SurvivalSettingsError
from terrabots.world_terrain import Cell, TerrainType, WorldGrid


def test_builtin_maps_load_and_are_playable() -> None:
    ids = {m["id"] for m in maps.catalog()}
    assert {"arena", "twin-hills", "ridge", "lakes", "fortress", "canyon", "badlands"} <= ids
    for i in ids:
        assert maps.check(maps.load(i)) == [], i


def test_round_trip_keeps_terrain(tmp_path) -> None:
    world = maps.load("lakes")
    data = maps.from_world(world, "Lakes copy")
    path = maps.save(data, tmp_path)
    again = maps.to_world(json.loads(path.read_text()))
    assert path.name == "lakes-copy.json"
    assert (again.elevation_map == world.elevation_map).all()
    assert again.get(12, 12).terrain is TerrainType.WATER


@pytest.mark.parametrize("change, message", [
    (lambda d: d.update(format="x"), "not a terrabots-map"),
    (lambda d: d.update(width=8), "width and height"),
    (lambda d: d["terrain"].__setitem__(0, "Q" * d["width"]), "unknown terrain letters"),
    (lambda d: d["elevation"].pop(), "elevation must be"),
])
def test_validation_says_whats_wrong(change, message) -> None:
    data = maps.from_world(WorldGrid(16, 16), "x")
    change(data)
    with pytest.raises(maps.MapError, match=message):
        maps.validate(data)


def test_check_finds_cut_off_areas() -> None:
    world = WorldGrid(32, 32)
    for y in range(32):
        world.set(16, y, Cell(TerrainType.ROCK, 5.0))         # wall from edge to edge
    assert any("can't be reached" in w for w in maps.check(world))


def test_battle_and_survival_on_a_map() -> None:
    from terrabots.agents.grazer import Grazer
    from terrabots.agents.sitting_duck import SittingDuck
    from terrabots.agents.tracker import Tracker

    runner = BattleRunner(BattleConfig(terrain="map", map="canyon", rounds=1, max_ticks_per_round=50),
                          [(Tracker, 1), (SittingDuck, 1)], time_budget_ms=None)
    assert (runner.world.width, runner.world.height) == (64, 40)
    runner.run()
    session = SurvivalSession(SurvivalSettings(terrain="map", map="arena", max_ticks=5), [(Grazer, 2)])
    assert session.world.width == 48


def test_map_terrain_needs_a_map() -> None:
    with pytest.raises(BattleConfigError, match="map"):
        BattleConfig(terrain="map")
    with pytest.raises(SurvivalSettingsError, match="map"):
        SurvivalSettings(terrain="map")
