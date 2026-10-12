"""Bots in their own processes: same results as before, hard limits, crashes."""

import pytest

from terrabots.battle import BattleConfig, BattleRunner
from terrabots.battle.config import BotEntry
from terrabots.battle.isolation import spec_of

FLAT = dict(terrain="flat", width=32, height=32, bot_isolation="process")


def test_process_battle_runs_and_is_reproducible() -> None:
    bots = [BotEntry("terrabots.agents.tracker:Tracker"), BotEntry("terrabots.agents.crazy:Crazy"),
            BotEntry("terrabots.agents.spin_bot:SpinBot")]

    def run() -> list:
        cfg = BattleConfig(rounds=2, seed=5, max_ticks_per_round=300, **FLAT)
        return BattleRunner(cfg, bots, time_budget_ms=None).run().rows

    first = run()
    assert first == run()
    assert sum(r["shots"] for r in first) > 0


def test_hanging_bot_is_killed_and_battle_continues() -> None:
    cfg = BattleConfig(rounds=1, max_ticks_per_round=20, **FLAT)
    runner = BattleRunner(cfg, [BotEntry("tests.isolation_bots:Hang"),
                                BotEntry("terrabots.agents.sitting_duck:SittingDuck")],
                          time_budget_ms=20)   # hard limit = 2 s
    results = runner.run()
    hang = next(r for r in results.rows if r["name"] == "Hang")
    assert hang["skipped_turns"] >= 1
    assert runner.processes == []          # closed after run()


def test_crashing_bot_in_process_is_switched_off() -> None:
    cfg = BattleConfig(rounds=1, max_ticks_per_round=20, **FLAT)
    results = BattleRunner(cfg, [BotEntry("tests.isolation_bots:Boom"),
                                 BotEntry("terrabots.agents.sitting_duck:SittingDuck")],
                           time_budget_ms=None).run()
    boom = next(r for r in results.rows if r["name"] == "Boom")
    assert boom["skipped_turns"] == 5


def test_memory_is_per_bot_process() -> None:
    cfg = BattleConfig(rounds=3, max_ticks_per_round=2, **FLAT)
    runner = BattleRunner(cfg, [BotEntry("tests.isolation_bots:Counter", 2)], time_budget_ms=None)
    for _ in range(3):
        runner.start_round()
        frame = runner.step()
        runner.end_round()
    runner.close()
    # Each process counted only its own rounds (in-process they'd share: 6).
    assert [frame["drawings"][i][0]["t"] for i in (0, 1)] == ["3", "3"]


def test_local_classes_cannot_be_isolated() -> None:
    class Local:  # noqa: D401
        pass

    with pytest.raises(ValueError, match="module level"):
        spec_of(Local)
