"""
Terrabots tournament: ranks every public bot and writes the leaderboard.

    python tools/tournament.py                 # full tournament -> docs/leaderboard.json / .md
    python tools/tournament.py --quick         # fewer rounds, for trying it out

Entrants are the battle bots and survival agents in terrabots/agents/, bots/
(the templates) and contrib/<author>/ (submissions, see CONTRIBUTING.md).

Three rankings:
- 1v1: every pair of battle bots plays on several maps. Ranked by APS, the
  average percentage score used by Robocode's RoboRumble: for each opponent,
  your share of the points scored in your battles against it, averaged over
  all opponents. 50 % means as good as the average opponent.
- Melee: all battle bots in one arena, several maps and seeds. Ranked by the
  average share of all points, times the number of bots (so 100 % = an equal
  share), plus round wins.
- Survival: all survival agents together in seeded worlds. Ranked by average
  lifetime in ticks, then survivors.

Every battle is seeded and every bot gets a fresh storage folder, so the
leaderboard is reproducible and bots that learn across battles start equal.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import itertools
import json
import os
import random
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DUEL_MAPS = [("flat", None), ("map", "twin-hills"), ("map", "ridge"), ("map", "fortress")]
MELEE_MAPS = [("flat", None), ("map", "lakes"), ("map", "fortress"), ("map", "canyon"), ("procedural", None)]


# ---------------------------------------------------------------------------
# Entrants
# ---------------------------------------------------------------------------

def _classes(module_name: str, base: type) -> list[type]:
    module = importlib.import_module(module_name)
    # Droids have no radar, so alone they can't see anyone: they belong in team
    # battles, which this ladder doesn't run (yet). _Names are helper classes.
    return [c for _, c in inspect.getmembers(module, inspect.isclass)
            if issubclass(c, base) and c is not base and c.__module__ == module_name
            and not inspect.isabstract(c) and not c.__name__.startswith("_")
            and not getattr(c, "droid", False)]


def entrants() -> tuple[list[dict], list[dict]]:
    """(battle bots, survival agents) as [{spec, name, origin}]."""
    from terrabots.battle.agent import BattleAgent
    from terrabots.framework.agent import Agent

    os.chdir(ROOT)
    modules = [(f"terrabots.agents.{p.stem}", "demo") for p in sorted((ROOT / "terrabots/agents").glob("*.py"))
               if p.stem != "__init__"]
    modules += [(f"bots.{p.stem}", "template") for p in sorted((ROOT / "bots").glob("*.py")) if p.stem != "__init__"]
    contrib = ROOT / "contrib"
    if contrib.is_dir():
        for p in sorted(contrib.glob("*/*.py")):
            if p.stem != "__init__":
                modules.append((f"contrib.{p.parent.name}.{p.stem}", f"contrib/{p.parent.name}"))
    battle, survival = [], []
    for module, origin in modules:
        try:
            for c in _classes(module, BattleAgent):
                battle.append({"spec": f"{module}:{c.__name__}", "name": c.__name__, "origin": origin,
                               "doc": (inspect.getdoc(c) or "").splitlines()[0] if inspect.getdoc(c) else ""})
            for c in _classes(module, Agent):
                survival.append({"spec": f"{module}:{c.__name__}", "name": c.__name__, "origin": origin,
                                 "doc": (inspect.getdoc(c) or "").splitlines()[0] if inspect.getdoc(c) else ""})
        except Exception as exc:          # a broken submission must not stop the tournament
            print(f"skipping {module}: {exc}", file=sys.stderr)
    return battle, survival


# ---------------------------------------------------------------------------
# Matches (run in worker processes)
# ---------------------------------------------------------------------------

def battle(specs: list[str], terrain: str, map_name: str | None, seed: int, rounds: int) -> dict:
    from terrabots.battle import BattleConfig, BattleRunner
    from terrabots.battle.config import BotEntry

    os.chdir(ROOT)
    cfg = BattleConfig(rounds=rounds, seed=seed, terrain=terrain, map=map_name)
    with tempfile.TemporaryDirectory() as data:
        rows = BattleRunner(cfg, [BotEntry(s) for s in specs], time_budget_ms=None, data_dir=data).run().rows
    # rows are named by class; specs here are distinct classes
    by_name = {r["name"]: r for r in rows}
    return {s: {"total": by_name[s.split(":")[1]]["total"], "firsts": by_name[s.split(":")[1]]["firsts"]}
            for s in specs}


def survival(specs: list[str], seed: int, ticks: int, per_class: int) -> dict:
    from terrabots.framework.simulation import SimConfig, Simulation
    from terrabots.map_generator import procedural
    from terrabots.battle.runner import load_bot_class  # noqa: F401  (sets sys.path for bots/)

    os.chdir(ROOT)
    random.seed(seed)
    sim = Simulation(procedural(48, 48, rng=random), SimConfig())
    classes = {}
    for s in specs:
        module, _, name = s.partition(":")
        cls = getattr(importlib.import_module(module), name)
        classes[cls.__name__] = s
        sim.add_agent(cls, count=per_class)
    snaps = sim.run(ticks=ticks)
    life, alive = defaultdict(int), defaultdict(int)
    for snap in snaps:
        for a in snap.agents:
            life[classes[a["class"]]] += a["alive"]
    for a in snaps[-1].agents:
        alive[classes[a["class"]]] += a["alive"]
    return {s: {"life": life[s], "alive": alive[s]} for s in specs}


def _run(job):
    kind, args = job
    return kind, args, (battle(*args) if kind != "survival" else survival(*args))


# ---------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Rank the public Terrabots bots.")
    ap.add_argument("--quick", action="store_true", help="fewer rounds and seeds")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--out", type=Path, default=ROOT / "docs")
    a = ap.parse_args()
    duel_rounds, melee_rounds, seeds = (3, 3, 1) if a.quick else (10, 10, 2)
    surv_seeds, surv_ticks = (4, 300) if a.quick else (16, 600)

    bots, agents = entrants()
    print(f"{len(bots)} battle bots, {len(agents)} survival agents")
    jobs = []
    for x, y in itertools.combinations([b["spec"] for b in bots], 2):
        for (terrain, m), s in itertools.product(DUEL_MAPS, range(seeds)):
            jobs.append(("duel", ([x, y], terrain, m, 1000 + s, duel_rounds)))
    for (terrain, m), s in itertools.product(MELEE_MAPS, range(seeds)):
        jobs.append(("melee", ([b["spec"] for b in bots], terrain, m, 2000 + s, melee_rounds)))
    for s in range(surv_seeds):
        jobs.append(("survival", ([g["spec"] for g in agents], 3000 + s, surv_ticks, 4)))

    t0 = time.time()
    pair_share: dict[tuple[str, str], list[float]] = defaultdict(list)
    duel_wins, duel_rounds_played = defaultdict(int), defaultdict(int)
    melee_share, melee_wins, melee_rounds_played = defaultdict(list), defaultdict(int), defaultdict(int)
    surv_life, surv_alive = defaultdict(int), defaultdict(int)
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for kind, args, res in pool.map(_run, jobs):
            if kind == "duel":
                x, y = args[0]
                total = res[x]["total"] + res[y]["total"] or 1.0
                pair_share[(x, y)].append(res[x]["total"] / total)
                pair_share[(y, x)].append(res[y]["total"] / total)
                for s in (x, y):
                    duel_wins[s] += res[s]["firsts"]
                    duel_rounds_played[s] += args[4]
            elif kind == "melee":
                total = sum(r["total"] for r in res.values()) or 1.0
                for s, r in res.items():
                    melee_share[s].append(r["total"] / total * len(res))
                    melee_wins[s] += r["firsts"]
                    melee_rounds_played[s] += args[4]
            else:
                for s, r in res.items():
                    surv_life[s] += r["life"]
                    surv_alive[s] += r["alive"]

    def entry(info: dict, **values) -> dict:
        return {"name": info["name"], "spec": info["spec"], "origin": info["origin"], "doc": info["doc"], **values}

    one_v_one = []
    for b in bots:
        opponents = [o["spec"] for o in bots if o["spec"] != b["spec"]]
        shares = [sum(pair_share[(b["spec"], o)]) / len(pair_share[(b["spec"], o)]) for o in opponents]
        one_v_one.append(entry(b, aps=round(100 * sum(shares) / len(shares), 1),
                               round_win_pct=round(100 * duel_wins[b["spec"]] / duel_rounds_played[b["spec"]], 1)))
    one_v_one.sort(key=lambda r: -r["aps"])
    melee = [entry(b, share=round(100 * sum(melee_share[b["spec"]]) / len(melee_share[b["spec"]]), 1),
                   round_win_pct=round(100 * melee_wins[b["spec"]] / melee_rounds_played[b["spec"]], 1))
             for b in bots]
    melee.sort(key=lambda r: -r["share"])
    per = surv_seeds * 4
    surv = [entry(g, avg_lifetime=round(surv_life[g["spec"]] / per, 1), survivors=surv_alive[g["spec"]],
                  of=per) for g in agents]
    surv.sort(key=lambda r: (-r["avg_lifetime"], -r["survivors"]))
    for table in (one_v_one, melee, surv):
        for i, r in enumerate(table, 1):
            r["rank"] = i

    from terrabots import __name__ as _pkg  # noqa: F401
    board = {
        "generated": time.strftime("%Y-%m-%d"),
        "seconds": round(time.time() - t0),
        "settings": {"duel_maps": [m or t for t, m in DUEL_MAPS], "melee_maps": [m or t for t, m in MELEE_MAPS],
                     "seeds": seeds, "duel_rounds": duel_rounds, "melee_rounds": melee_rounds,
                     "survival_worlds": surv_seeds, "survival_ticks": surv_ticks, "quick": a.quick},
        "one_v_one": one_v_one, "melee": melee, "survival": surv,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    old = a.out / "leaderboard.json"
    if old.exists():
        previous = json.loads(old.read_text())
        same = all(previous.get(k) == board[k] for k in ("settings", "one_v_one", "melee", "survival"))
        if same:          # nothing changed: keep the file (and its date) as it is
            print("Results unchanged.")
            return
    (a.out / "leaderboard.json").write_text(json.dumps(board, indent=1) + "\n")
    (a.out / "leaderboard.md").write_text(markdown(board))
    print(markdown(board))


def markdown(board: dict) -> str:
    s = board["settings"]
    out = [f"# Leaderboard", "",
           f"Generated {board['generated']} by `tools/tournament.py`. Every battle is seeded; learning bots start "
           "with empty storage. Submit your bot: see [CONTRIBUTING.md](../CONTRIBUTING.md#submit-a-bot).", "",
           "## 1v1", "",
           f"Every pair, maps {', '.join(s['duel_maps'])}, {s['seeds']} seeds x {s['duel_rounds']} rounds. "
           "APS = average percentage score against each opponent (RoboRumble's measure; 50 = even).", "",
           "| # | Bot | APS | Rounds won | From |", "|---|---|---|---|---|"]
    out += [f"| {r['rank']} | {r['name']} | {r['aps']} | {r['round_win_pct']} % | {r['origin']} |" for r in board["one_v_one"]]
    out += ["", "## Melee", "", f"All bots together, maps {', '.join(s['melee_maps'])}, {s['seeds']} seeds x "
            f"{s['melee_rounds']} rounds. Share: points scored, 100 % = an equal share.", "",
            "| # | Bot | Share | Rounds won | From |", "|---|---|---|---|---|"]
    out += [f"| {r['rank']} | {r['name']} | {r['share']} % | {r['round_win_pct']} % | {r['origin']} |" for r in board["melee"]]
    out += ["", "## Survival", "", f"All agents together (4 each), {s['survival_worlds']} worlds x "
            f"{s['survival_ticks']} ticks.", "", "| # | Agent | Avg lifetime | Survivors | From |", "|---|---|---|---|---|"]
    out += [f"| {r['rank']} | {r['name']} | {r['avg_lifetime']} ticks | {r['survivors']} / {r['of']} | {r['origin']} |"
            for r in board["survival"]]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
