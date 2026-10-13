"""Sandboxed bots: what a malicious bot can't do, and that honest ones play normally.

Needs Docker and the sandbox image (docker build -t terrabots-sandbox -f
docker/sandbox.Dockerfile docker/); skipped otherwise. The wire and discovery
tests at the bottom run everywhere.
"""

import math
import textwrap
from pathlib import Path

import pytest

from terrabots.battle import BattleAction, BattleConfig, BattleObservation, BattleRunner
from terrabots.battle import wire
from terrabots.battle.isolation import BotProcessError
from terrabots.battle.sandbox import SandboxEntry, SandboxError, SandboxBot, bot_mount, check_available, find_bots
from terrabots.world_terrain import WorldGrid

try:
    check_available()
    HAVE_SANDBOX = True
except SandboxError:
    HAVE_SANDBOX = False
needs_docker = pytest.mark.skipif(not HAVE_SANDBOX, reason="Docker or the terrabots-sandbox image is missing")

HEADER = '''
from terrabots.battle import BattleAction, BattleAgent

def report(agent, *facts):
    for f in facts:
        agent.draw.text(0, 0, str(f)[:80])
'''

EVIL = {
    "probe": '''
class Probe(BattleAgent):
    """Tries to get out: network, other folders, writing, its own profile."""
    def decide(self, obs):
        import os, socket
        from terrabots.world_terrain import CreatureMoveProfile
        self.profile = CreatureMoveProfile(max_climb_per_step=1000.0)
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=1); report(self, "net:open")
        except OSError:
            report(self, "net:blocked")
        report(self, "bot:" + ",".join(sorted(os.listdir("/bot"))))
        report(self, "submissions:" + ",".join(sorted(os.listdir("/bot/submissions"))))
        for path in ("/engine/terrabots/evil.py", "/bot/submissions/mallory/x.py", "/evil"):
            try:
                open(path, "w").write("x"); report(self, "write:" + path)
            except OSError:
                report(self, "readonly:" + path)
        report(self, "uid:%d" % os.getuid())
        return BattleAction()
''',
    "looper": '''
class Looper(BattleAgent):
    """Never answers."""
    def decide(self, obs):
        while True:
            pass
''',
    "hog": '''
class Hog(BattleAgent):
    """Eats all memory."""
    def decide(self, obs):
        blocks = []
        while True:
            blocks.append(bytearray(64 * 1024 * 1024))
''',
    "liar": '''
class Liar(BattleAgent):
    """Sends replies the engine must reject."""
    def decide(self, obs):
        if obs.tick % 2:
            return BattleAction(velocity=float("nan"))
        self.draw.shapes = [{"k": "text", "x": 0, "y": 0, "t": "x" * 5000, "c": "#fff"}]
        return BattleAction()
''',
    "flood": '''
class Flood(BattleAgent):
    """One enormous reply."""
    def decide(self, obs):
        self.colors = {"body": "#" + "f" * 3_000_000}
        self.draw.shapes = [{"k": "text", "x": 0, "y": 0, "t": "y" * 2_000_000, "c": "#fff"}]
        return BattleAction()
''',
    "honest": '''
from terrabots.battle.geometry import normalize_angle

class Honest(BattleAgent):
    """Aims at what it sees; prints a little."""
    def on_round_start(self, round_number, rounds):
        self.colors = {"body": "#cc3366"}
        self.storage.save("rounds", {"last": round_number})
    def decide(self, obs):
        print("tick", obs.tick)
        if not obs.scanned_bots:
            return BattleAction(velocity=0.3, body_turn=5, gun_turn=20)
        e = obs.scanned_bots[0]
        return BattleAction(velocity=0.4, gun_turn=normalize_angle(e.bearing - obs.gun_heading), fire=1.0)
''',
}


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    for author in ("alice", "mallory"):
        d = tmp_path / "submissions" / author
        d.mkdir(parents=True)
        (d / "__init__.py").write_text("")
    for name, body in EVIL.items():
        (tmp_path / "submissions" / "mallory" / f"{name}.py").write_text(HEADER + textwrap.dedent(body))
    (tmp_path / "submissions" / "alice" / "secret.py").write_text("SECRET = 42\n")
    return tmp_path


def one_turn(bot: SandboxBot, tick: int = 1, budget_ms: float | None = None) -> BattleAction:
    bot.bot_id, bot.name, bot.rules = 0, "bot", BattleConfig()
    if tick == 1:
        bot.on_round_start(1, 1)
    obs = BattleObservation(tick=tick, round=1, bot_id=0, x=10.0, y=10.0, heading=0.0, gun_heading=0.0,
                            radar_heading=0.0, velocity=0.0, energy=100.0, gun_heat=0.0, elevation=0.0,
                            arena_width=32, arena_height=32, others=1)
    bot.request_decide(obs)
    return bot.collect_decide(budget_ms)


@needs_docker
def test_probe_finds_no_way_out(root: Path) -> None:
    bot = SandboxBot(SandboxEntry("submissions.mallory.probe:Probe", root), WorldGrid(32, 32), 1)
    try:
        one_turn(bot)
        facts = {s["t"] for s in bot.draw.shapes}
    finally:
        bot.close()
    assert "net:blocked" in facts
    assert "submissions:mallory" in facts            # alice's folder (and her secret) isn't there
    assert {"readonly:/engine/terrabots/evil.py", "readonly:/bot/submissions/mallory/x.py",
            "readonly:/evil"} <= facts
    assert "uid:10001" in facts
    assert bot.profile.max_climb_per_step == 2.0     # its own profile never reaches the engine


@needs_docker
def test_bot_that_never_answers_is_stopped(root: Path) -> None:
    bot = SandboxBot(SandboxEntry("submissions.mallory.looper:Looper", root), WorldGrid(32, 32), 1)
    with pytest.raises(BotProcessError, match="no answer"):
        one_turn(bot, budget_ms=20)
    assert bot.is_dead
    bot.close()


@needs_docker
def test_memory_hog_is_killed(root: Path) -> None:
    bot = SandboxBot(SandboxEntry("submissions.mallory.hog:Hog", root), WorldGrid(32, 32), 1)
    with pytest.raises(BotProcessError):
        one_turn(bot)
    bot.close()


@needs_docker
def test_bad_replies_are_rejected(root: Path) -> None:
    bot = SandboxBot(SandboxEntry("submissions.mallory.liar:Liar", root), WorldGrid(32, 32), 1)
    try:
        with pytest.raises(BotProcessError, match="finite"):
            one_turn(bot, tick=1)                     # NaN velocity
        with pytest.raises(BotProcessError, match="drawing text"):
            one_turn(bot, tick=2)                     # oversized text
    finally:
        bot.close()


@needs_docker
def test_huge_reply_stops_the_bot(root: Path) -> None:
    bot = SandboxBot(SandboxEntry("submissions.mallory.flood:Flood", root), WorldGrid(32, 32), 1)
    with pytest.raises(BotProcessError):
        one_turn(bot)
    assert bot.is_dead
    bot.close()


@needs_docker
def test_battle_goes_on_without_misbehaving_bots(root: Path) -> None:
    from terrabots.agents.sitting_duck import SittingDuck

    cfg = BattleConfig(rounds=1, seed=3, terrain="flat", width=32, height=32, max_ticks_per_round=200)
    entries = [(SandboxEntry(f"submissions.mallory.{m}:{c}", root), 1)
               for m, c in (("looper", "Looper"), ("liar", "Liar"), ("honest", "Honest"))]
    results = BattleRunner(cfg, entries + [(SittingDuck, 1)], time_budget_ms=20).run()
    by = {r["name"]: r for r in results.rows}
    assert by["Honest"]["shots"] > 0
    assert by["Looper"]["skipped_turns"] > 0 and by["Liar"]["skipped_turns"] > 0


@needs_docker
def test_sandboxed_battle_is_reproducible(root: Path) -> None:
    from terrabots.agents.tracker import Tracker

    def run():
        cfg = BattleConfig(rounds=2, seed=5, terrain="flat", max_ticks_per_round=400)
        return BattleRunner(cfg, [(SandboxEntry("submissions.mallory.honest:Honest", root), 1), (Tracker, 1)],
                            time_budget_ms=None).run().rows

    assert run() == run()


@needs_docker
def test_sandboxed_team_messages(root: Path) -> None:
    """Team data and messages cross the sandbox: a sandboxed droid aims with its leader's reports."""
    import shutil

    import terrabots.agents.squad as squad
    from terrabots.agents.sitting_duck import SittingDuck

    d = root / "submissions" / "bob"
    d.mkdir()
    (d / "__init__.py").write_text("")
    shutil.copy(squad.__file__, d / "squad.py")
    cfg = BattleConfig(rounds=1, seed=1, terrain="flat", width=32, height=32, max_ticks_per_round=300)
    runner = BattleRunner(cfg, [(SittingDuck, 1)], time_budget_ms=None, teams=[("Blue", [
        (squad.SquadLeader, 1), (SandboxEntry("submissions.bob.squad:SquadDroid", root), 1)])])
    rows = runner.run().rows
    droid = next(r for r in rows if r["name"] == "SquadDroid")
    assert droid["hits"] > 0


@needs_docker
def test_sandboxed_survival_agent(root: Path) -> None:
    import random

    from terrabots.battle.sandbox import SandboxAgent
    from terrabots.framework.simulation import Simulation
    from terrabots.map_generator import procedural

    d = root / "submissions" / "carol"
    d.mkdir()
    (d / "__init__.py").write_text("")
    import terrabots.agents.grazer as grazer
    (d / "grazer.py").write_text(Path(grazer.__file__).read_text())
    random.seed(2)
    sim = Simulation(procedural(24, 24, rng=random))
    sim.add_agent(SandboxAgent.factory(SandboxEntry("submissions.carol.grazer:Grazer", root), seed=2), count=2)
    try:
        snaps = sim.run(ticks=60)
    finally:
        sim.close()
    assert {a["class"] for a in snaps[-1].agents} == {"Grazer"}
    assert len(snaps) == 60 or snaps[-1].n_alive == 0


# --- without Docker -------------------------------------------------------------

def test_mount_is_the_authors_folder_only(root: Path) -> None:
    host, inside = bot_mount(SandboxEntry("submissions.mallory.probe:Probe", root))
    assert host == (root / "submissions" / "mallory").resolve() and inside == "/bot/submissions/mallory"


def test_symlinked_submission_is_refused(root: Path, tmp_path_factory) -> None:
    elsewhere = tmp_path_factory.mktemp("private")
    (root / "submissions" / "eve").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(SandboxError, match="symlink"):
        bot_mount(SandboxEntry("submissions.eve.bot:Bot", root))


def test_find_bots_reads_without_importing(tmp_path: Path) -> None:
    f = tmp_path / "bots.py"
    f.write_text(textwrap.dedent('''
        raise SystemExit("importing me would be a mistake")
        from terrabots.battle import BattleAgent
        from terrabots.battle.robocode import Droid, TeamRobot
        from terrabots.framework.agent import Agent

        class _Base(BattleAgent):
            pass

        class Leader(_Base):
            """Leads."""

        class Helper(Droid, TeamRobot):
            """Helps."""

        class Small(_Base):
            droid = True

        class Forager(Agent):
            """Eats."""

        class NotABot:
            pass
    '''))
    found = {b.name: b for b in find_bots(f, "pkg.bots")}
    assert set(found) == {"Leader", "Helper", "Small", "Forager"}
    assert found["Leader"].kind == "battle" and found["Leader"].doc == "Leads." and not found["Leader"].droid
    assert found["Helper"].droid and found["Small"].droid
    assert found["Forager"].kind == "survival" and found["Forager"].spec == "pkg.bots:Forager"


@pytest.mark.parametrize("reply, msg", [
    ({"velocity": float("inf")}, "finite"),
    ({"fire": "3"}, "finite"),
    ({"shout": {"recipient_id": 1, "kind": "x" * 100}}, "shout.kind"),
    ({"shout": {"recipient_id": 1, "payload": {"a": "x" * 10_000}}}, "bytes"),
    ("not an object", "object"),
])
def test_wire_rejects_bad_actions(reply, msg) -> None:
    with pytest.raises(wire.WireError, match=msg):
        wire.battle_action_in(reply)


def test_wire_round_trips_observations() -> None:
    from terrabots.battle.events import ScannedBot, TeamMessage

    obs = BattleObservation(tick=3, round=1, bot_id=0, x=1.5, y=2.5, heading=10, gun_heading=20, radar_heading=30,
                            velocity=0.2, energy=99, gun_heat=0, elevation=1, arena_width=32, arena_height=32,
                            others=2, scanned_bots=[ScannedBot(1, "a", "A", 90, 5, 0, 0.1, 100, 0, True)],
                            team_messages=[TeamMessage(2, "b", {"x": [1, 2]})])
    back = wire.battle_obs_in(wire.parse_line(__import__("json").dumps(wire.battle_obs_out(obs))))
    assert back == obs
    assert math.isclose(wire.battle_action_in({"velocity": 0.5}).velocity, 0.5)


def test_setup_screen_lists_community_bots_without_importing(tmp_path: Path, monkeypatch) -> None:
    import sys

    from terrabots.battle.discovery import discover_bots

    d = tmp_path / "contrib" / "dan"
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("raise SystemExit('imported!')\n")
    (d / "bot.py").write_text("raise SystemExit('imported!')\nclass Dan(BattleAgent):\n    \"\"\"Dan's bot.\"\"\"\n")
    monkeypatch.chdir(tmp_path)
    found = {b.spec: b for b in discover_bots()}
    assert found["contrib.dan.bot:Dan"].sandboxed and found["contrib.dan.bot:Dan"].doc == "Dan's bot."
    assert "contrib.dan.bot" not in sys.modules
