"""Persistent bot storage: per class, JSON, quota, in-process and in a bot process."""

import pytest

from terrabots.battle import BattleAction, BattleAgent, BattleConfig, BattleRunner
from terrabots.battle.config import BotEntry
from terrabots.battle.storage import BotStorage


def test_save_load_round_trip(tmp_path) -> None:
    s = BotStorage(tmp_path, "pkg.Bot")
    assert s.load("stats", default={}) == {}
    assert s.save("stats", {"wins": 3})
    assert BotStorage(tmp_path, "pkg.Bot").load("stats") == {"wins": 3}   # survives a new instance


def test_quota_refuses_and_keeps_old_file(tmp_path) -> None:
    s = BotStorage(tmp_path, "pkg.Bot", quota_kb=1)
    assert s.save("a", "x" * 500)
    assert not s.save("b", "y" * 800)            # 500 + 800 > 1024
    assert s.load("b") is None and s.load("a") == "x" * 500
    assert s.save("a", "z" * 900)                # replacing a file counts only the new size


def test_bad_names_rejected(tmp_path) -> None:
    with pytest.raises(ValueError):
        BotStorage(tmp_path, "pkg.Bot").save("../escape", 1)


def test_in_memory_without_data_dir() -> None:
    s = BotStorage(None, "pkg.Bot")
    assert s.save("x", [1, 2]) and s.load("x") == [1, 2]


def test_bots_count_battles_across_runs(tmp_path) -> None:
    for isolation in ("none", "process"):
        data = tmp_path / isolation
        for _ in range(2):
            cfg = BattleConfig(rounds=1, max_ticks_per_round=3, terrain="flat", bot_isolation=isolation)
            BattleRunner(cfg, [BotEntry("tests.isolation_bots:Remember"),
                               BotEntry("terrabots.agents.sitting_duck:SittingDuck")],
                         time_budget_ms=None, data_dir=str(data)).run()
        stored = BotStorage(data, "tests.isolation_bots.Remember").load("count")
        assert stored == 2, isolation
