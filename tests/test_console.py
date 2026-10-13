"""Bot consoles: prints, self.log and the bot's own loggers reach the viewer frames."""

import pytest

from terrabots.battle import BattleConfig, BattleRunner
from terrabots.battle.config import BotEntry
from terrabots.console import capture, is_users_bot


def test_only_users_bots_count_as_owned() -> None:
    assert is_users_bot("bots.my_tank") and is_users_bot("mubot.battle.bot")
    assert not is_users_bot("terrabots.agents.tracker")


@pytest.mark.parametrize("isolation", ["none", "process"])
def test_console_lines_reach_the_frame(isolation) -> None:
    cfg = BattleConfig(rounds=1, max_ticks_per_round=4, terrain="flat", bot_isolation=isolation)
    runner = BattleRunner(cfg, [BotEntry("tests.isolation_bots:Chatty"),
                                BotEntry("terrabots.agents.sitting_duck:SittingDuck")],
                          time_budget_ms=None, console=True)
    runner.start_round()
    frames = [runner.step() for _ in range(3)]
    runner.close()
    lines = [l for f in frames for l in f["console"].get(0, [])]
    assert lines == ["hello from print", "tick 2", "[info] from the logger"]
    assert all(1 not in f["console"] for f in frames)        # built-in bot: not captured


def test_lines_are_capped() -> None:
    class Loud:
        _console = []

    with capture(Loud()) as lines:
        for i in range(100):
            print("x" * 1000)
    assert len(lines) == 30 and all(len(l) <= 301 for l in lines)
