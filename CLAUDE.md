# CLAUDE.md — Terrabots

Briefing for Claude Code. Read this first; `docs/arena-spec.md` is the battle-mode
spec (built, with the open decisions listed in its §9).

## What this is

Terrabots is a Python framework for writing autonomous agents ("bots") that compete in a
2.5D world: a grid with per-cell elevation and water depth, elevation-aware line of
sight, and range- and LOS-gated communication. Think Robocode for teaching Python, AI,
statistics and ML. MIT-licensed, author André Munzinger. Intended for public
educational/research use, so readability for learners matters as much as features.

Two game modes:
- **Survival mode** (built): agents forage food, pay metabolism, communicate, die at
  0 energy.
- **Battle mode** (built): Robocode-style tanks with body/gun/radar headings,
  bullets, rounds, scoring, a browser setup screen and results table
  (`terrabots-battle`). See `docs/arena-spec.md`.

## Owner's working preferences (apply to all work here)

- Incremental changes; preserve architecture; smallest viable change. Explain the
  current behaviour and intended impact before modifying non-trivial code.
- For multi-file / architectural work: short plan + assumptions + trade-offs first,
  then confirm before building.
- Never invent APIs, library behaviour or test results. Say what was tested versus
  what only looks correct. State uncertainty explicitly.
- Simple > clever. SRP, explicit interfaces, no speculative abstractions.
  Comments explain *why*, not *what*.
- Direct, neutral communication; no filler.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

pytest -q                                      # 104 tests, all passing as of 2026-10-12
docker compose up --build -d                   # battle :8765 + survival :8766 in Docker
terrabots-battle                               # battle setup screen → http://localhost:8765/
terrabots-battle battles/example.toml --headless   # results table + results/*.json/csv
terrabots-run                                  # survival sim + viewer → http://localhost:8765/
terrabots-run --headless --ticks 500 --seed 1  # no browser
terrabots-run --agent bots.wanderer:WandererAgent=5 --agent mubot:MuBotAgent=5   # needs private mubot repo installed
terrabots-run --help
```

VS Code: `.vscode/` has launch configs (F5: run with viewer, debug `bots/wanderer`,
headless, debug current test), tasks (setup venv, run tests, open
viewer), test-explorer settings, and extension recommendations.

## Layout

```
terrabots/
  world_terrain.py      WorldGrid, Cell, TerrainType, CreatureMoveProfile,
                        VisibilityMgr (LOS), MovementResolver (passability, move cost)
  comms.py              CommsMgr: shout-range + LOS gated, per-tick mailbox
  map_generator.py      procedural() and flat() terrain, explicit rng
  framework/            survival mode: Agent, Action, Observation, Simulation
  battle/
    config.py           BattleConfig (all rules, validated) + BattleFile (TOML)
    physics.py          BattleBody, kinematics, radar arc, bullet geometry (pure functions)
    arena.py            Arena: one round, tick loop, events, damage, deaths
    scoring.py          Robocode-like scoring per round
    runner.py           BattleRunner: rounds, totals, BattleResults (JSON/CSV/table)
    agent.py, actions.py, observation.py, events.py, geometry.py   bot-facing API
    robocode.py         AdvancedRobot: Robocode's queued-command API for ported bots
    isolation.py        ProcessBot: one process per bot (bot_isolation = "process")
    debug.py            DebugCanvas behind agent.draw (Robocode onPaint)
    storage.py          BotStorage behind agent.storage: JSON per bot class, quota
    discovery.py        finds BattleAgent subclasses in bots/ and terrabots/agents/
    cli.py              terrabots-battle
  agents/               demo battle bots: SittingDuck, SpinBot, Tracker, Crazy, Walls,
                        RamFire, Corners (uses storage), Learner (GF gun, storage);
                        Grazer (survival)
  viewer/               index.html + server.py (survival, broadcast-only);
                        battle.html + battle_server.py (bidirectional, setup/results)
  run.py                terrabots-run (survival CLI)
bots/                   user bots: first_tank.py (battle template), wanderer.py (survival)
battles/example.toml    example battle file
docs/                   arena-spec.md; index.html + assets/ = GitHub Pages landing page
tests/                  pytest, one function per rule/scenario
```

## Core design invariants (don't break these without discussing)

1. **Synchronous ticks.** All agents `decide()` on the same pre-tick state, then
   actions are applied. Order in `Simulation.step()`: observations + on_message →
   all decide → clear comms → apply actions (move, forage, shout) → metabolism/death →
   deliver messages → regen resources → snapshot.
2. **Messages sent in tick N are readable in tick N+1** (mailbox; `deliver()` after
   actions, `clear()` before the next sends).
3. **LOS = elevation only.** No terrain type blocks sight by itself. Rock blocks
   because it is tall. Intermediate Bresenham cells are compared to the interpolated
   sightline (eye height = cell elevation + `eye_height_offset`). A squared-distance
   cull runs before any raycast.
4. **`WorldGrid.elevation_map` (numpy) must mirror `Cell.elevation`.** `WorldGrid.set()`
   keeps them in sync; anything writing `cell.elevation` directly (e.g. `run.py`
   terrain generation) must also write `elevation_map[x, y]`. There's no observer, on
   purpose.
5. **Comms need both** `distance ≤ max_shout_range` (independent of sight range) **and**
   LOS.
6. **Climbing:** a move is impassable if elevation gain > `max_climb_per_step`;
   climbing costs `climb_cost_multiplier × gain` extra energy.
7. **Agents only see what they perceive.** `Observation` is range- and LOS-filtered;
   never hand agents global state.
8. Resources live in `Simulation._resources` (`{(x, y): amount}`), not on cells.
9. **Battle tick order** (`Arena.step`, Robocode's loop per RoboWiki): observe +
   decide (timed; process bots in parallel) → move bullets (incl. last tick's) →
   cool/fire (gun heading before turning) → turn → move bodies (walls, rams) →
   radar → inactivity drain → deaths → comms. Events reach bots one tick later.
10. **Battle perception:** other bots only via radar (`scanned_bots`) and events;
    terrain via a range-limited `TerrainView`. Headings are Robocode's (0 = north,
    clockwise). Robocode px values convert at `PX_PER_CELL = 16`.
11. **Determinism:** same seed + same bots → identical results, as long as no turn
    is skipped for time. Tests pass `time_budget_ms=None`.

## Current status (2026-10-12)

Verified:
- `pytest`: 104 passed (terrain, comms, survival sim, battle config, physics incl.
  the RoboWiki rules, arena, runner determinism, Robocode API, process isolation,
  CLI, battle server WebSocket round trip).
- Headless battles of the demo bots (~8.5k ticks/s with 6 bots in-process; process
  isolation is ~4x slower because of the per-tick pipe round trips).
- Docker: `docker compose up` in the private mubot repo served both viewers;
  checked over HTTP and in headless Chromium.
- Battle viewer and survival viewer driven in headless Chromium (Playwright,
  SwiftShader) with Three.js 0.186.1 from jsDelivr: setup → battle → results work,
  no console errors. **Not yet checked in a real desktop browser / GPU.**
- Landing page (`docs/index.html`) rendered at 1366 px and 390 px, no overflow.

Decisions taken with the spec defaults (spec §9), not yet confirmed by André:
hybrid continuous-on-grid; hit energy return = damage dealt; radar-only
perception; disabled at exactly 0 energy (firing is capped at remaining energy,
which is how a bot reaches 0; spec §4 originally said such a shot is rejected,
which made "disabled" unreachable); free-for-all only. Changed later to follow
Robocode: radar range 75 cells (was 25), 36 px square hitbox (was 0.45-cell
circle), kill bonus on all damage to the victim (RoboWiki wording, read literally).

## Known issues / tech debt (prioritised)

1. MuBot (battle port of the Java bot + survival version) lives in the private
   repo (`../mubot`, `devbyandre/terrabots_mubot`); never add MuBot code here.
2. Teams and `foraging_enabled` (survival rules inside battles) are not built.
3. Process isolation is not a sandbox (see SECURITY.md); the Python API defaults
   to in-process so notebook/test-local bots work.
4. Bullets hit-test in 2D (flight height only matters for terrain blocking).
   Bodies are axis-aligned squares (Robocode); every covered cell must be enterable.
5. Tanks are procedural low-poly meshes; the Quaternius GLB was never used.
6. Survival `world_state()` still sends one JSON dict per cell.
7. Survival observations: terrain LOS is cached per cell, but filling the cache
   costs ~3 ms per new cell (exact Bresenham per target). A vectorised or
   shadow-casting LOS would be faster but must keep invariant 3's results.
8. `_random_passable_cell` rebuilds the occupied set on every attempt.
9. No map file loader; no Gymnasium/PettingZoo wrapper.

## Next work

Teams (postponed by André), map files, Gymnasium wrapper, faster survival LOS.

## Conventions

- Python ≥ 3.11, type hints everywhere, dataclasses for plain data, `from __future__
  import annotations`.
- New features come with tests in `tests/`. Seeded randomness for anything
  asserted on.
- Bot spec format everywhere (CLI, UI, configs): `package.module:ClassName[=count]`.
- Keep `bots/wanderer.py` as the smallest working example; it's the first file a
  learner reads.
- Commit messages: imperative, explain why. No Claude co-author / session
  trailers (André's rule; history was rewritten to remove them).
