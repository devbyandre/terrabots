"""Arena and BattleRunner integration: radar LOS, energy economics, rounds, determinism."""

import random
import time

import pytest

from terrabots.battle import BattleAction, BattleAgent, BattleConfig, BattleObservation, BattleRunner
from terrabots.battle.arena import Arena
from terrabots.battle.physics import ALIVE, DEAD, DISABLED
from terrabots.world_terrain import Cell, TerrainType, WorldGrid


class Duck(BattleAgent):
    def decide(self, obs: BattleObservation) -> BattleAction:
        return BattleAction()


class Gunner(BattleAgent):
    """Fires `power` along its current gun heading whenever the gun is cool."""
    power = 3.0

    def decide(self, obs: BattleObservation) -> BattleAction:
        return BattleAction(fire=self.power)


class Scanner(BattleAgent):
    adjust_radar_for_gun_turn = True
    adjust_gun_for_body_turn = True

    def on_round_start(self, round_number: int, rounds: int) -> None:
        self.seen: list[int] = []

    def decide(self, obs: BattleObservation) -> BattleAction:
        self.seen += [s.bot_id for s in obs.scanned_bots]
        return BattleAction(radar_turn=10)


def make_arena(world: WorldGrid, agents: list[BattleAgent], placements, **cfg) -> Arena:
    """Arena with bots moved to fixed (x, y, gun_heading, radar_heading) placements."""
    cfg.setdefault("initial_gun_heat", 0.0)
    config = BattleConfig(**cfg)
    for i, a in enumerate(agents):
        a.bot_id = i
        a.on_round_start(1, 1)
    arena = Arena(config, world, agents, 1, random.Random(0))
    for slot, (x, y, gun, radar) in zip(arena.slots.values(), placements):
        b = slot.body
        b.x, b.y, b.heading, b.gun_heading, b.radar_heading = x, y, 0.0, gun, radar
    return arena


def wall_world() -> WorldGrid:
    """32x20 flat world with a tall wall at x=10 and stairs (elev 6) at x=16."""
    world = WorldGrid(32, 20)
    for y in range(20):
        world.set(10, y, Cell(TerrainType.ROCK, elevation=3.0))
    world.set(16, 10, Cell(TerrainType.STAIRS, elevation=6.0))
    return world


# --- radar ----------------------------------------------------------------

def test_bot_behind_rock_not_scanned() -> None:
    scanner = Scanner()
    arena = make_arena(wall_world(), [scanner, Duck()],
                       [(5.5, 10.5, 0, 85), (14.5, 10.5, 0, 0)])
    arena.step()
    arena.step()
    assert scanner.seen == []


def test_bot_on_stairs_scanned_over_rock() -> None:
    scanner = Scanner()
    arena = make_arena(wall_world(), [scanner, Duck()],
                       [(5.5, 10.5, 0, 85), (16.5, 10.5, 0, 0)])
    arena.step()
    arena.step()
    assert scanner.seen == [1]


def test_radar_los_can_be_switched_off() -> None:
    scanner = Scanner()
    arena = make_arena(wall_world(), [scanner, Duck()],
                       [(5.5, 10.5, 0, 85), (14.5, 10.5, 0, 0)], radar_requires_los=False)
    arena.step()
    arena.step()
    assert scanner.seen == [1]


# --- bullets and energy -----------------------------------------------------

def run_until_hit(arena: Arena, max_ticks: int = 50) -> None:
    for _ in range(max_ticks):
        frame = arena.step()
        if any(e["type"] == "bullet_hit" for e in frame["events"]):
            return
    raise AssertionError("no hit")


@pytest.mark.parametrize("mode, shooter_energy", [
    ("damage", 100 - 3 + 16), ("robocode", 100 - 3 + 9), ("none", 100 - 3)])
def test_energy_economics(mode: str, shooter_energy: float) -> None:
    arena = make_arena(WorldGrid(20, 20), [Gunner(), Duck()],
                       [(5.5, 10.5, 90, 90), (10.5, 10.5, 0, 0)], hit_energy_return=mode)
    run_until_hit(arena)
    shooter, target = arena.slots[0].body, arena.slots[1].body
    assert shooter.energy == pytest.approx(shooter_energy)
    assert target.energy == pytest.approx(100 - 16)


def test_gun_heat_blocks_second_shot() -> None:
    arena = make_arena(WorldGrid(20, 20), [Gunner(), Duck()],
                       [(5.5, 10.5, 0, 0), (15.5, 10.5, 0, 0)])
    arena.step()
    assert arena.scorer.scores[0].shots == 1
    assert arena.slots[0].body.gun_heat == pytest.approx(1 + 3 / 5)
    for _ in range(10):
        arena.step()
    assert arena.scorer.scores[0].shots == 1  # 1.6 heat / 0.1 per tick = 16 ticks


def test_hill_blocks_bullet_from_low_ground() -> None:
    world = WorldGrid(20, 20)
    world.set(8, 10, Cell(TerrainType.PLAIN, elevation=2.0))  # hill between the bots
    arena = make_arena(world, [Gunner(), Duck()], [(5.5, 10.5, 90, 90), (11.5, 10.5, 0, 0)])
    for _ in range(20):
        arena.step()
    assert arena.slots[1].body.energy == 100
    assert arena.scorer.scores[0].hits == 0


def test_firing_to_zero_disables_and_next_hit_kills() -> None:
    gunner = Gunner()
    arena = make_arena(WorldGrid(20, 20), [gunner, Gunner()],
                       [(5.5, 10.5, 270, 0), (10.5, 10.5, 270, 0)])
    arena.slots[0].body.energy = 2.0   # fires away from target, power capped at 2
    arena.step()
    assert arena.slots[0].body.state == DISABLED
    run_until_hit(arena)
    assert arena.slots[0].body.state == DEAD


def test_ramming_damages_both_and_scores_rammer() -> None:
    class Rammer(BattleAgent):
        def decide(self, obs):
            return BattleAction(velocity=0.5)

    arena = make_arena(WorldGrid(20, 20), [Rammer(), Duck()],
                       [(10.5, 5.5, 0, 0), (10.5, 7.0, 0, 0)])
    for _ in range(10):
        arena.step()
    assert arena.slots[1].body.energy < 100
    assert arena.scorer.scores[0].ram_damage > 0


# --- runner ---------------------------------------------------------------

def test_same_seed_same_results() -> None:
    from terrabots.agents.crazy import Crazy
    from terrabots.agents.spin_bot import SpinBot
    from terrabots.agents.tracker import Tracker

    def run() -> str:
        cfg = BattleConfig(rounds=2, seed=11, max_ticks_per_round=400)
        return BattleRunner(cfg, [(Tracker, 1), (SpinBot, 1), (Crazy, 1)],
                            time_budget_ms=None).run().to_json()

    assert run() == run()


def test_memory_survives_rounds() -> None:
    class Counter(BattleAgent):
        def on_round_start(self, round_number, rounds):
            self.memory["rounds"] = self.memory.get("rounds", 0) + 1

        def decide(self, obs):
            return BattleAction()

    runner = BattleRunner(BattleConfig(rounds=3, max_ticks_per_round=5, terrain="flat"),
                          [(Counter, 2)], time_budget_ms=None)
    runner.run()
    assert runner.memory[Counter]["rounds"] == 6  # shared by both instances, 3 rounds


def test_slow_bot_turns_are_skipped() -> None:
    class Slow(BattleAgent):
        def decide(self, obs):
            time.sleep(0.01)
            return BattleAction(fire=1)

    runner = BattleRunner(BattleConfig(rounds=1, max_ticks_per_round=5, terrain="flat"),
                          [(Slow, 1), (Duck, 1)], time_budget_ms=2)
    results = runner.run()
    slow = next(r for r in results.rows if r["name"] == "Slow")
    assert slow["skipped_turns"] == 5
    assert slow["shots"] == 0


def test_crashing_bot_switched_off_after_five_errors() -> None:
    class Broken(BattleAgent):
        calls = 0

        def decide(self, obs):
            Broken.calls += 1
            raise RuntimeError("boom")

    runner = BattleRunner(BattleConfig(rounds=1, max_ticks_per_round=20, terrain="flat"),
                          [(Broken, 1), (Duck, 1)], time_budget_ms=None)
    runner.run()
    assert Broken.calls == 5


def test_results_rank_by_total_and_export() -> None:
    from terrabots.agents.tracker import Tracker

    runner = BattleRunner(BattleConfig(rounds=2, seed=3, max_ticks_per_round=600, terrain="flat"),
                          [(Tracker, 1), (Duck, 2)], time_budget_ms=None)
    results = runner.run()
    totals = [r["total"] for r in results.rows]
    assert totals == sorted(totals, reverse=True)
    assert [r["rank"] for r in results.rows] == [1, 2, 3]
    assert results.to_csv().splitlines()[0].startswith("rank,name,total")
    assert sum(r["firsts"] for r in results.rows) == 2


def test_survival_points_for_outliving_enemies() -> None:
    world = WorldGrid(20, 20)
    arena = make_arena(world, [Gunner(), Duck(), Duck()],
                       [(5.5, 10.5, 90, 90), (8.5, 10.5, 0, 0), (15.5, 15.5, 0, 0)])
    arena.slots[1].body.energy = 1.0
    run_until_hit(arena)
    assert arena.slots[1].body.state == DEAD
    assert arena.scorer.scores[0].survival == 50
    assert arena.scorer.scores[2].survival == 50
    assert arena.slots[2].body.state == ALIVE
