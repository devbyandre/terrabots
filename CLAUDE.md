# CLAUDE.md — Terrabots

Briefing for Claude Code. Read this first, then `docs/arena-spec.md` for the next
major feature.

## What this is

Terrabots is a Python framework for writing autonomous agents ("bots") that compete in a
2.5D world: a grid with per-cell elevation and water depth, elevation-aware line of
sight, and range- and LOS-gated communication. Think Robocode for teaching Python, AI,
statistics and ML. MIT-licensed, author André Munzinger. Intended for public
educational/research use, so readability for learners matters as much as features.

Two game modes:
- **Survival mode** (built): agents forage food, pay metabolism, communicate, die at
  0 energy.
- **Battle mode** (spec only): Robocode-style tanks with body/gun/radar headings,
  bullets, rounds, scoring, a battle setup UI. See `docs/arena-spec.md`.

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

pytest -q                                   # 11 tests, all passing as of 2026-10-12
terrabots-run                                  # sim + viewer → open http://localhost:8765/
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
  framework/
    agent.py            Agent ABC: decide(obs) -> Action; on_birth/on_message/on_death
    actions.py          Action, MoveDirection, Shout
    observation.py      Observation + percept dataclasses; to_dict() for RL
    simulation.py       Simulation: tick loop, observations, foraging, regen, snapshots
  agents/               Built-in demo bots (empty; planned). MuBot is private, see below
  viewer/server.py      HTTP (index.html) + WebSocket (/ws) on one port, broadcast-only
  viewer/index.html     Three.js r128 viewer: flat-shaded terrain, box agents, HUD
  run.py                CLI entry point (terrabots-run), procedural terrain, --agent specs
bots/                   User bots (Robocode "robots" dir). wanderer.py = template
tests/                  test_world_terrain.py, test_comms.py (script-style scenarios
                        wrapped by one pytest function each), test_simulation.py
docs/arena-spec.md      Battle mode spec: next major feature
.vscode/                Launch / tasks / settings
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

## Current status (2026-10-12)

Verified:
- `pytest`: 11 passed (6 terrain LOS/movement scenarios, 7 comms scenarios run
  inside 2 wrapper tests, 9 simulation integration tests).
- Headless runs with mixed bot classes via `--agent`.
- Viewer server: HTTP 200 for `/`, WebSocket sends `world_state` then `tick` messages
  (checked with a Python client).
- Viewer page rendered in headless Chromium (software GL) with a local copy of
  three@0.128.0 substituted for the CDN: terrain, agents, resources and HUD show,
  no console errors. **Not yet checked in a real desktop browser loading Three.js
  from jsDelivr.**

## Known issues / tech debt (prioritised)

1. **Food never respawns.** `_regen_resources()` only grows existing cells; a cell
   eaten to 0 is deleted for good, so every world eventually starves (seen in a
   200-tick run: resources 53 → 0). Fix: spawn new resource cells at a configurable
   rate on PLAIN/STAIRS cells (add `ResourceConfig.spawn_rate`).
2. **No built-in opponents.** MuBot lives in a private sibling repo (`../mubot`,
   `devbyandre/terrabots_mubot`) and must not be added here. The public framework only ships
   `bots/wanderer.py`; demo/test bots (`terrabots/agents/`) are still to do.
3. *(moved to the private mubot repo: MuBot port caveats)*
4. Viewer agents are box placeholders. The Quaternius CC0 tank GLB
   (https://poly.pizza/m/Dc4k4CooN3) isn't wired in yet; check its node structure
   (separate turret?) first.
5. Three.js pinned to r128 (2021). Upgrade when doing battle UI (see spec §11).
6. `world_state()` sends one JSON dict per cell, which is heavy beyond ~64×64. Move to
   flat arrays.
7. Per-tick observation cost: the terrain-percept loop does an LOS raycast for every
   cell within perception radius for every agent (≈ agents × π r²). Fine for tens of
   agents; cache per-agent visible cells or skip terrain percepts if it becomes the
   bottleneck. Profile before optimising.
8. `_random_passable_cell` rebuilds the occupied set on every attempt (O(n) each).
9. `test_world_terrain.py` / `test_comms.py` are script-style scenarios behind one
   pytest wrapper each. Split into individual `test_*` functions for clearer failures.
10. `Observation.to_dict()` is a flat dict, not a Gymnasium `spaces` definition. A real
    Gymnasium/PettingZoo wrapper is still to do.
11. No map file loader yet (only procedural terrain in `run.py`). Candidate home:
    `terrabots/map_generator.py`, with procedural generation moved out of `run.py`.
12. No CI, no linter config beyond VS Code's ruff recommendation, no git remote yet.

## Next work

Primary: **battle mode**, implemented in the order of `docs/arena-spec.md` §12. Check
the open decisions in §9 with André before step 2 (kinematics), because they shape
the data model.

Quick wins before or alongside it: known issues #1 (food respawn) and #9 (split
tests), then a GitHub Actions workflow running `pytest` on 3.11–3.13.

## Conventions

- Python ≥ 3.11, type hints everywhere, dataclasses for plain data, `from __future__
  import annotations`.
- New features come with tests in `tests/`. Seeded randomness for anything
  asserted on.
- Bot spec format everywhere (CLI, UI, configs): `package.module:ClassName[=count]`.
- Keep `bots/wanderer.py` as the smallest working example; it's the first file a
  learner reads.
- Commit messages: imperative, explain why.
