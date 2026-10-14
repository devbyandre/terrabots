"""Robocode bots (Java jars) through adapters/robocode: they load, aim, move and talk.

Needs javac (to build the test jars) plus Docker and the terrabots-sandbox-robocode
image; skipped otherwise.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from terrabots.battle import BattleConfig, BattleRunner
from terrabots.battle.sandbox import ROBOCODE_IMAGE, JarEntry, SandboxError, check_available

ROOT = Path(__file__).resolve().parents[1]
BOTS = Path(__file__).with_name("robocode")

try:
    check_available(ROBOCODE_IMAGE)
    READY = shutil.which("javac") is not None and shutil.which("jar") is not None
except SandboxError:
    READY = False
pytestmark = pytest.mark.skipif(not READY, reason="needs javac, Docker and the terrabots-sandbox-robocode image")

ROBOCODE_FIELD = dict(terrain="flat", width=50, height=37, hit_energy_return="robocode")


@pytest.fixture(scope="module")
def jars(tmp_path_factory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("jars")
    classes = out / "classes"
    sources = [str(p) for p in (ROOT / "adapters/robocode/src").rglob("*.java")]
    sources += [str(p) for p in (BOTS / "src").rglob("*.java")]
    subprocess.run(["javac", "--release", "17", "-Xlint:-options", "-d", str(classes), *sources], check=True)
    made = {}
    for props in BOTS.glob("*.properties"):
        name = props.stem
        stage = out / name / "tbtest"
        stage.mkdir(parents=True)
        shutil.copy(classes / "tbtest" / f"{name}.class", stage)
        shutil.copy(props, stage)
        made[name] = out / f"{name}.jar"
        subprocess.run(["jar", "--create", "--file", str(made[name]), "-C", str(out / name), "."], check=True)
    return made


def entry(jars, name) -> JarEntry:
    found = JarEntry.from_jar(jars[name])
    assert [e.spec for e in found] == [f"robocode:tbtest.{name}"]
    return found[0]


def test_jar_declares_its_robot(jars) -> None:
    e = entry(jars, "Locker")
    assert e.class_name == "Locker" and e.jar == jars["Locker"].resolve()


def test_basic_and_advanced_robots_fight(jars) -> None:
    from terrabots.agents.sitting_duck import SittingDuck

    cfg = BattleConfig(rounds=2, seed=1, max_ticks_per_round=900, **ROBOCODE_FIELD)
    rows = {r["name"]: r for r in BattleRunner(cfg, [(entry(jars, "Walker"), 1), (entry(jars, "Locker"), 1),
                                                     (SittingDuck, 1)], time_budget_ms=None).run().rows}
    # Locker spins its radar with Double.POSITIVE_INFINITY, locks on and aims.
    assert rows["Locker"]["hits"] > 5 and rows["Locker"]["hit_rate"] > 0.2
    assert rows["Walker"]["shots"] > 0           # blocking ahead()/turnGunRight()/fire()
    assert rows["Locker"]["skipped_turns"] == 0


def test_java_team_talks(jars) -> None:
    """The droid has no radar; it can only hit with the spotter's messages."""
    from terrabots.agents.sitting_duck import SittingDuck

    cfg = BattleConfig(rounds=1, seed=2, max_ticks_per_round=500, **ROBOCODE_FIELD)
    runner = BattleRunner(cfg, [(SittingDuck, 1)], time_budget_ms=None,
                          teams=[("Java", [(entry(jars, "Spotter"), 1), (entry(jars, "Gunner"), 1)])])
    arena = runner.start_round()
    assert sorted(s.body.energy for s in arena.slots.values()) == [100.0, 120.0, 200.0]
    while not arena.over:
        runner.step()
    runner.end_round()
    runner.close()
    gunner = next(r for r in runner.results().rows if r["name"] == "Gunner")
    assert gunner["hits"] > 0


def test_cli_runs_a_jar(jars, tmp_path, capsys) -> None:
    from terrabots.battle.cli import main

    main(["--headless", "--rounds", "1", "--seed", "3", "--jar", str(jars["Locker"]),
          "--bot", "terrabots.agents.sitting_duck:SittingDuck", "--results-dir", str(tmp_path)])
    assert "Locker" in capsys.readouterr().out
