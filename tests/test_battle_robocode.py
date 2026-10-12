"""Robocode-style AdvancedRobot API: queued commands, remaining amounts, events."""

import random

import pytest

from terrabots.battle import BattleAction, BattleAgent, BattleConfig
from terrabots.battle.arena import Arena
from terrabots.battle.robocode import AdvancedRobot
from terrabots.world_terrain import WorldGrid


class Duck(BattleAgent):
    def decide(self, obs):
        return BattleAction()


def arena_with(bot: BattleAgent, other_xy=(30.5, 10.5), bot_xy=(10.5, 10.5), **cfg) -> Arena:
    cfg.setdefault("initial_gun_heat", 0.0)
    config = BattleConfig(**cfg)
    agents = [bot, Duck()]
    for i, a in enumerate(agents):
        a.bot_id, a.rules = i, config
        a.on_round_start(1, 1)
    arena = Arena(config, WorldGrid(48, 30), agents, 1, random.Random(0))
    for slot, (x, y) in zip(arena.slots.values(), (bot_xy, other_xy)):
        slot.body.x, slot.body.y = x, y
        slot.body.heading = slot.body.gun_heading = slot.body.radar_heading = 0.0
    return arena


def test_radar_turn_runs_over_several_ticks_and_reports_completion() -> None:
    class Spinner(AdvancedRobot):
        done_at = None

        def tick(self):
            if self.time == 1:
                self.set_turn_radar_right(360)

        def on_radar_turn_complete(self):
            if self.time > 1 and Spinner.done_at is None:   # level-triggered, like Robocode
                Spinner.done_at = self.time

    arena = arena_with(Spinner())
    for _ in range(12):
        arena.step()
    assert Spinner.done_at == 9        # turned in ticks 1-8 (8 x 45°), reported in tick 9
    assert arena.slots[0].body.radar_heading == pytest.approx(0.0)


def test_set_ahead_drives_the_distance_and_stops() -> None:
    class Driver(AdvancedRobot):
        def tick(self):
            if self.time == 1:
                self.set_ahead(6.0)

    arena = arena_with(Driver())
    for _ in range(60):
        arena.step()
    body = arena.slots[0].body
    assert body.velocity == 0
    assert body.y == pytest.approx(10.5 + 6.0, abs=0.05)


def test_scan_event_bearing_is_relative_to_body() -> None:
    class Looker(AdvancedRobot):
        seen = []

        def tick(self):
            self.set_turn_radar_right(45)

        def on_scanned_robot(self, e):
            Looker.seen.append((e.name, round(e.bearing), round(e.absolute_bearing)))

    arena = arena_with(Looker())
    for _ in range(4):
        arena.step()
    assert ("Duck", 90, 90) in Looker.seen   # body faces north, target due east


def test_fired_bullet_gets_id_and_hit_event_returns_it() -> None:
    class Shooter(AdvancedRobot):
        fired = []
        hits = []

        def on_round_start(self, round_number, rounds):
            self.set_adjust_gun_for_robot_turn(True)

        def tick(self):
            if self.time == 1:
                self.set_turn_gun_right(90)
            elif self.gun_turn_remaining == 0 and not Shooter.fired:
                b = self.set_fire(3)
                if b:
                    Shooter.fired.append(b)

        def on_bullet_hit(self, e):
            Shooter.hits.append(e)

    arena = arena_with(Shooter(), other_xy=(16.5, 10.5))
    for _ in range(30):
        arena.step()
    assert Shooter.fired and Shooter.fired[0].bullet_id is not None
    assert Shooter.hits and Shooter.hits[0].bullet is Shooter.fired[0]
    assert Shooter.hits[0].bullet.active is False


def test_wall_hit_clears_distance_remaining() -> None:
    class Rammer(AdvancedRobot):
        def tick(self):
            if self.time == 1:
                self.set_ahead(100)

    arena = arena_with(Rammer(), bot_xy=(10.5, 25.5))
    for _ in range(40):
        arena.step()
    assert arena.slots[0].agent.distance_remaining == 0
