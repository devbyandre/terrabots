"""Team battles: leader and droid energy, friendly fire, team messages, team scoring."""

import random

import pytest

from terrabots.battle import BattleAction, BattleAgent, BattleConfig, BattleObservation, BattleRunner
from terrabots.battle.arena import Arena
from terrabots.battle.config import BattleConfigError, BattleFile, BotEntry, TeamEntry
from terrabots.battle.physics import DEAD
from terrabots.battle.robocode import Droid, MessageEvent, TeamRobot
from terrabots.world_terrain import Cell, TerrainType, WorldGrid


class Duck(BattleAgent):
    def decide(self, obs: BattleObservation) -> BattleAction:
        return BattleAction()


class Gunner(BattleAgent):
    def decide(self, obs: BattleObservation) -> BattleAction:
        return BattleAction(fire=3.0)


class Scanner(BattleAgent):
    adjust_radar_for_gun_turn = True
    adjust_gun_for_body_turn = True

    def on_round_start(self, round_number: int, rounds: int) -> None:
        self.seen: list[tuple[int, bool]] = []

    def decide(self, obs: BattleObservation) -> BattleAction:
        self.seen += [(s.bot_id, s.teammate) for s in obs.scanned_bots]
        return BattleAction(radar_turn=45)


class DroidScanner(Scanner):
    droid = True


class Talker(BattleAgent):
    """Broadcasts its tick; records what it hears as (tick heard, sender, data)."""

    def on_round_start(self, round_number: int, rounds: int) -> None:
        self.heard: list[tuple[int, int, object]] = []

    def decide(self, obs: BattleObservation) -> BattleAction:
        self.heard += [(obs.tick, m.sender_id, m.data) for m in obs.team_messages]
        self.broadcast({"tick": obs.tick, "from": self.name})
        return BattleAction()


def team_arena(world, agents, teams, placements, **cfg) -> Arena:
    """Arena with bots on fixed (x, y, gun_heading, radar_heading); teams[i] is bot i's team."""
    cfg.setdefault("initial_gun_heat", 0.0)
    members: dict = {}
    for i, t in enumerate(teams):
        if t is not None:
            members.setdefault(t, []).append(i)
    for i, (a, t) in enumerate(zip(agents, teams)):
        a.bot_id, a.name = i, f"bot{i}"
        a.team = t
        a.teammates = {o: f"bot{o}" for o in members.get(t, []) if o != i}
        a.is_leader = t is not None and len(members[t]) > 1 and members[t][0] == i
        a.on_round_start(1, 1)
    arena = Arena(BattleConfig(**cfg), world, agents, 1, random.Random(0))
    for slot, (x, y, gun, radar) in zip(arena.slots.values(), placements):
        b = slot.body
        b.x, b.y, b.heading, b.gun_heading, b.radar_heading = x, y, 0.0, gun, radar
    return arena


# --- energy and radar ------------------------------------------------------

def test_leader_and_droid_start_energy() -> None:
    arena = team_arena(WorldGrid(32, 32), [Duck(), DroidScanner(), Duck()], ["A", "A", None],
                       [(5.5, 5.5, 0, 0), (10.5, 10.5, 0, 0), (25.5, 25.5, 0, 0)])
    energies = [s.body.energy for s in arena.slots.values()]
    assert energies == [200.0, 120.0, 100.0]


def test_droid_has_no_radar() -> None:
    droid, scanner = DroidScanner(), Scanner()
    arena = team_arena(WorldGrid(32, 32), [droid, scanner, Duck()], [None, None, None],
                       [(5.5, 16.5, 0, 0), (12.5, 16.5, 0, 0), (20.5, 16.5, 0, 0)])
    for _ in range(10):
        arena.step()
    assert droid.seen == []
    assert scanner.seen


def test_scans_mark_teammates() -> None:
    scanner = Scanner()
    arena = team_arena(WorldGrid(32, 32), [scanner, Duck(), Duck()], ["A", "A", "B"],
                       [(16.5, 16.5, 0, 0), (16.5, 24.5, 0, 0), (16.5, 8.5, 0, 0)])
    for _ in range(10):
        arena.step()
    assert set(scanner.seen) == {(1, True), (2, False)}


# --- friendly fire ------------------------------------------------------------

def test_friendly_fire_hurts_but_scores_nothing() -> None:
    # Gunner faces north (gun heading 0) at its teammate 5 cells away.
    arena = team_arena(WorldGrid(32, 32), [Gunner(), Duck(), Duck()], ["A", "A", "B"],
                       [(16.5, 10.5, 0, 0), (16.5, 15.5, 0, 0), (5.5, 28.5, 0, 0)],
                       team_leader_bonus=0.0)
    for _ in range(12):
        arena.step()
    shooter, mate = arena.slots[0], arena.slots[1]
    assert mate.body.energy < 100.0                       # it hurt
    assert arena.scorer.scores[0].bullet_damage == 0.0     # no points
    assert arena.scorer.scores[0].hits == 0
    # no energy back: only what firing cost has changed
    assert shooter.body.energy == pytest.approx(100.0 - 3.0 * arena.scorer.scores[0].shots)


def test_enemy_hit_still_scores() -> None:
    arena = team_arena(WorldGrid(32, 32), [Gunner(), Duck()], ["A", "B"],
                       [(16.5, 10.5, 0, 0), (16.5, 15.5, 0, 0)])
    for _ in range(12):
        arena.step()
    assert arena.scorer.scores[0].bullet_damage > 0


# --- messages -------------------------------------------------------------

def test_team_messages_arrive_next_tick_and_only_for_teammates() -> None:
    a, b, enemy = Talker(), Talker(), Talker()
    arena = team_arena(WorldGrid(32, 32), [a, b, enemy], ["A", "A", "B"],
                       [(5.5, 5.5, 0, 0), (25.5, 25.5, 0, 0), (5.5, 25.5, 0, 0)])
    for _ in range(3):
        arena.step()
    assert b.heard[:2] == [(2, 0, {"tick": 1, "from": "bot0"}), (3, 0, {"tick": 2, "from": "bot0"})]
    assert all(sender == 1 for _, sender, _ in a.heard)
    assert enemy.heard == []                      # its team has no one else


def test_send_to_one_teammate() -> None:
    class Whisper(BattleAgent):
        def decide(self, obs: BattleObservation) -> BattleAction:
            self.send("bot2", "psst")
            return BattleAction()

    w, left_out, target = Whisper(), Talker(), Talker()
    arena = team_arena(WorldGrid(32, 32), [w, left_out, target], ["A", "A", "A"],
                       [(5.5, 5.5, 0, 0), (25.5, 25.5, 0, 0), (5.5, 25.5, 0, 0)])
    arena.step()
    arena.step()
    assert [d for _, s, d in target.heard if s == 0] == ["psst"]
    assert [d for _, s, d in left_out.heard if s == 0] == []


def test_message_range_and_line_of_sight() -> None:
    world = WorldGrid(40, 20)
    for y in range(12, 20):                       # a rock wall in the north half only
        world.set(9, y, Cell(TerrainType.ROCK, elevation=6.0))
    near, far, behind_rock = Talker(), Talker(), Talker()
    arena = team_arena(world, [Talker(), near, far, behind_rock], ["A"] * 4,
                       [(5.5, 10.5, 0, 0), (10.5, 10.5, 0, 0), (5.5, 1.5, 0, 0), (11.5, 14.5, 0, 0)],
                       team_message_range=8.0)
    arena.step()
    arena.step()
    heard_from_0 = lambda bot: [d for _, s, d in bot.heard if s == 0]   # noqa: E731
    assert heard_from_0(near)                 # 5 cells, clear view
    assert heard_from_0(far) == []            # 9 cells: out of range
    assert heard_from_0(behind_rock) == []    # 7.2 cells, in range, but the rock is in the way


def test_unlimited_range_by_default() -> None:
    world = WorldGrid(40, 20)
    for y in range(20):
        world.set(20, y, Cell(TerrainType.ROCK, elevation=6.0))
    behind_rock = Talker()
    arena = team_arena(world, [Talker(), behind_rock], ["A", "A"],
                       [(5.5, 10.5, 0, 0), (35.5, 10.5, 0, 0)])
    arena.step()
    arena.step()
    assert [d for _, s, d in behind_rock.heard if s == 0]


def test_messages_must_be_plain_data() -> None:
    t = Talker()
    t.teammates = {1: "x"}
    t.broadcast({"ok": [1, 2.5, "a", None]})
    t.broadcast(object())                          # not JSON: dropped
    t.broadcast("x" * 10_000)                      # too big: dropped
    assert t.take_outbox() == [(None, {"ok": [1, 2.5, "a", None]})]


# --- round end and scoring -------------------------------------------------

def test_round_ends_when_one_team_is_left() -> None:
    arena = team_arena(WorldGrid(32, 32), [Duck(), Duck(), Duck()], ["A", "A", "B"],
                       [(5.5, 5.5, 0, 0), (25.5, 25.5, 0, 0), (5.5, 25.5, 0, 0)])
    assert not arena.over
    arena.slots[2].body.energy, arena.slots[2].body.state = 0.0, DEAD
    arena.step()
    assert arena.over
    ranking = arena.finish()
    assert ranking[-1] == 2
    s = arena.scorer.scores
    assert s[0].survival == s[1].survival == 50.0          # an enemy died
    assert s[0].last_survivor == s[1].last_survivor == 10.0  # 10 per enemy bot
    assert s[0].firsts == s[1].firsts == 1 and s[2].seconds == 1


def test_teammate_death_gives_no_survival_points() -> None:
    arena = team_arena(WorldGrid(32, 32), [Duck(), Duck(), Duck(), Duck()], ["A", "A", "B", "B"],
                       [(5.5, 5.5, 0, 0), (25.5, 25.5, 0, 0), (5.5, 25.5, 0, 0), (25.5, 5.5, 0, 0)])
    arena.slots[1].body.energy, arena.slots[1].body.state = 0.0, DEAD
    arena.step()
    s = arena.scorer.scores
    assert s[0].survival == 0.0 and s[2].survival == s[3].survival == 50.0
    assert not arena.over


def test_solo_battle_results_unchanged_by_team_code() -> None:
    """A battle without teams must score exactly as before teams existed."""
    from terrabots.agents.crazy import Crazy
    from terrabots.agents.tracker import Tracker

    cfg = BattleConfig(rounds=2, seed=5, terrain="flat", max_ticks_per_round=800)
    rows = BattleRunner(cfg, [(Tracker, 2), (Crazy, 1)], time_budget_ms=None).run().rows
    again = BattleRunner(cfg, [(Tracker, 2), (Crazy, 1)], teams=[], time_budget_ms=None).run().rows
    assert rows == again
    assert all(r["team"] is None for r in rows)


def test_team_battle_results_and_table() -> None:
    from terrabots.agents.crazy import Crazy
    from terrabots.agents.squad import SquadDroid, SquadLeader

    cfg = BattleConfig(rounds=3, seed=2, terrain="flat", max_ticks_per_round=1500)
    runner = BattleRunner(cfg, [(Crazy, 1)], time_budget_ms=None,
                          teams=[("Blue", [(SquadLeader, 1), (SquadDroid, 2)])])
    results = runner.run()
    assert [r["name"] for r in results.teams] and {r["name"] for r in results.teams} == {"Blue", "Crazy"}
    blue = next(r for r in results.teams if r["name"] == "Blue")
    assert blue["members"] == ["SquadLeader", "SquadDroid (1)", "SquadDroid (2)"]
    assert blue["total"] == pytest.approx(sum(r["total"] for r in results.rows if r["team"] == "Blue"), abs=0.1)
    assert sum(r["firsts"] for r in results.teams) == 3
    assert "members" in results.table()
    assert '"teams"' in results.to_json()


# --- battle files -------------------------------------------------------------

def test_battle_file_teams_round_trip() -> None:
    import tomllib

    bf = BattleFile.from_dict({"rounds": 2, "bots": [{"spec": "a:B"}],
                               "teams": [{"name": "Red", "members": [{"spec": "x:Lead"}, {"spec": "x:Droid", "count": 2}]}]})
    assert bf.teams == [TeamEntry("Red", [BotEntry("x:Lead", 1), BotEntry("x:Droid", 2)])]
    again = BattleFile.from_dict(tomllib.loads(bf.to_toml()))
    assert again.teams == bf.teams and again.bots == bf.bots


@pytest.mark.parametrize("teams, msg", [
    ([{"name": "", "members": [{"spec": "a:B"}]}], "name"),
    ([{"name": "A", "members": []}], "at least one member"),
    ([{"name": "A", "members": [{"spec": "a:B"}]}, {"name": "A", "members": [{"spec": "a:B"}]}], "twice"),
    ([{"name": "A", "members": [{"count": 2}]}], "spec"),
])
def test_bad_teams_are_rejected(teams, msg) -> None:
    with pytest.raises(BattleConfigError, match=msg):
        BattleFile.from_dict({"teams": teams})


# --- Robocode TeamRobot and processes -------------------------------------------

def test_team_robot_messages() -> None:
    class Chatty(TeamRobot):
        def on_round_start(self, round_number: int, rounds: int) -> None:
            self.got: list[MessageEvent] = []

        def tick(self) -> None:
            self.broadcast_message({"hi": self.name})

        def on_message_received(self, e: MessageEvent) -> None:
            self.got.append(e)

    class ChattyDroid(Droid, Chatty):
        pass

    a, b = Chatty(), ChattyDroid()
    arena = team_arena(WorldGrid(32, 32), [a, b, Duck()], ["A", "A", None],
                       [(5.5, 5.5, 0, 0), (25.5, 25.5, 0, 0), (5.5, 25.5, 0, 0)])
    arena.step()
    arena.step()
    assert b.got and b.got[0] == MessageEvent("bot0", {"hi": "bot0"})
    assert a.get_teammates() == ["bot1"] and a.is_teammate("bot1") and not a.is_teammate(2)
    assert arena.slots[1].body.energy == 120.0


def test_team_battle_in_processes() -> None:
    from terrabots.agents.squad import SquadDroid, SquadLeader
    from terrabots.agents.sitting_duck import SittingDuck

    cfg = BattleConfig(rounds=1, seed=1, terrain="flat", width=32, height=32,
                       max_ticks_per_round=300, bot_isolation="process")
    runner = BattleRunner(cfg, [(SittingDuck, 1)], time_budget_ms=None,
                          teams=[("Blue", [(SquadLeader, 1), (SquadDroid, 1)])])
    arena = runner.start_round()
    energies = sorted(s.body.energy for s in arena.slots.values())
    assert energies == [100.0, 120.0, 200.0]
    while not arena.over:
        runner.step()
    runner.end_round()
    runner.close()
    # The droid can only have hit the duck with the leader's reports.
    droid = next(r for r in runner.results().rows if r["name"] == "SquadDroid")
    assert droid["hits"] > 0
