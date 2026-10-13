# Battle Arena — Specification

Status: **implemented 2026-10-12** (steps 1–9 of §12 except the MuBot port, which
lives in a private repo). Deviations from this text: radar range default 25
cells; firing is capped at remaining energy so a bot can shoot itself to exactly
0 and become disabled (§4); `foraging_enabled` not built; procedural tanks
instead of the GLB (§11). It describes the
Robocode-style battle mode requested on 2026-10-12. Defaults marked *(decision)*
were chosen as defaults so work could start and can be overridden — see
[§9 Open decisions](#9-open-decisions).

## 1. Goal

A Robocode-like experience on top of the existing Terrabots world:

1. A **battle setup screen** in the browser: pick bots, how many of each, and battle
   settings (arena size, rounds, round length, bullet and energy rules, radar).
2. **Watch the battle** live in the 3D viewer: bodies, turrets, bullets, radar
   sweeps, energy bars, scoreboard; pause/step/speed controls.
3. **Results table** at the end of the battle, like Robocode's results dialog.
4. The same battles runnable **headless from the CLI / VS Code** for tournaments,
   statistics and ML training.

Survival mode (foraging, metabolism, comms — what exists today) stays as it is.
Battle mode is a second game mode sharing terrain, LOS, and comms.

## 2. Architecture decision: hybrid continuous-on-grid *(decision)*

Robocode bodies move continuously with headings; the current framework moves agents
one grid cell per tick in 8 directions. Radar sweeps, aiming and bullet travel do
not work well on discrete cells.

| Option | Description | Verdict |
|---|---|---|
| A. Hybrid | Positions become floats; `cell = (floor(x), floor(y))` for terrain, elevation, passability, LOS. Bodies, bullets, radar are continuous. | **Chosen.** Keeps all terrain/LOS/comms code; Robocode-faithful feel. |
| B. Pure grid | Bullets advance N cells/tick; radar = 8 sectors. | Simpler, but aiming and radar become coarse; MuBot-style targeting (GuessFactor) loses meaning. |
| C. Separate engine | New continuous engine, no terrain. | Throws away the 2.5D work. |

Consequences of A:
- New `BattleAgent` base class with its own `BattleObservation` / `BattleAction`.
  Survival `Agent` is untouched. (Separation of concerns; no flag-driven branching
  inside one class.)
- One cell = one distance unit. Robocode uses pixels (bots are 36 px, max speed 8
  px/tick); scale all Robocode-derived numbers by a configurable `units_per_cell`
  rather than hardcoding pixels.
- Movement must re-check `MovementResolver.can_pass(..., from_pos=...)` whenever the
  body crosses into a new cell (climb limit, rock, deep water still apply).

## 3. Battle settings (`BattleConfig`)

One dataclass, loadable from TOML (`battles/*.toml`, Python 3.11 `tomllib`), editable
in the setup screen, sent over the WebSocket as JSON. All values validated on load
(ranges below); invalid config is rejected with a message naming the field.

| Group | Field | Default | Range / notes |
|---|---|---|---|
| Arena | `width`, `height` | 48, 48 | 16–256 cells |
| | `terrain` | `"procedural"` | `"procedural"`, `"flat"`, or a map file path (map loader still TODO) |
| | `seed` | `null` | int → reproducible terrain, spawns and RNG |
| Rounds | `rounds` | 10 | 1–1000 |
| | `max_ticks_per_round` | 2000 | round ends at this tick even with several survivors |
| | `tick_delay_ms` | 30 | viewer playback only; headless ignores it |
| Bodies | `initial_energy` | 100 | |
| | `max_velocity` | 0.5 cells/tick | Robocode: 8 px/tick |
| | `acceleration` / `deceleration` | 0.05 / 0.1 | Robocode: 1 / 2 px/tick² |
| | `max_body_turn_deg` | 10 − 0.75·\|v\| scaled | Robocode formula, velocity in px |
| | `max_gun_turn_deg` | 20 | per tick |
| | `body_half_width` | 1.125 cells | square hitbox (Robocode 36 px), axis-aligned, for bullets, rams and terrain |
| Gun | `min_bullet_power` / `max_bullet_power` | 0.1 / 3.0 | |
| | `bullet_speed` | formula `20 − 3·power` px/tick, scaled | or a fixed override `bullet_speed_fixed` |
| | `max_bullet_speed` | cap, optional | the "max speed of bullets" setting |
| | `damage_formula` | `"robocode"`: `4·p`, plus `2·(p−1)` if p > 1 | or `"linear"`: `damage_per_power · p` |
| | `max_damage` | `null` | optional cap applied after the formula |
| | `gun_heat_per_shot` | `1 + p/5` | can't fire while heat > 0 |
| | `gun_cooling_rate` | 0.1 / tick | |
| | `hit_energy_return` | `"damage"` *(decision)* | see §4 |
| Radar | `radar_range` | 75 cells | Robocode: 1200 px |
| | `max_radar_turn_deg` | 45 | per tick |
| | `radar_requires_los` | `true` | uses existing elevation-aware `VisibilityMgr` |
| Mode | `foraging_enabled` | `false` | survival food/metabolism inside battles |
| | `comms_enabled` | `true` | existing range+LOS shouting, for team bots later |
| | `decide_time_budget_ms` | 20 | over budget → turn skipped (see §8) |

Robocode reference values above are from general knowledge of Robocode's rules, not
checked against its source in this session. Verify against the Robocode docs /
RoboWiki before treating them as authoritative.

## 4. Energy economics

As requested: **firing a bullet of power `p` costs `p` energy immediately. If it hits,
the target loses `damage(p)` and the shooter gains energy.**

`hit_energy_return` options:
- `"damage"` *(default, André's rule)*: shooter gains exactly the damage dealt.
- `"robocode"`: shooter gains `3·p` (Robocode's actual rule).
- `"none"`: no return.

**Balance warning:** with `"damage"` and the Robocode damage formula, a power-3 shot
costs 3 and returns 16, so an accurate bot gains +13 per hit. That makes accuracy
much more valuable than in Robocode and rewards spraying max-power shots. This is
expected for this rule, not a bug, but expect different winning strategies. The
`"robocode"` option exists so the two can be compared.

Further rules (Robocode-like):
- A bot whose energy would drop to ≤ 0 from firing cannot fire (shot rejected).
- At exactly 0 energy a bot is **disabled** (can't move or fire) but not dead; it dies
  when hit. *(decision; Robocode behaviour)*
- Collision with terrain the body can't enter: stop, small damage
  `wall_damage = max(0, |v|·0.5 − 1)` scaled. Ramming another bot: 0.6 damage to each,
  scored as ram damage for the rammer.
- With `foraging_enabled`, metabolism and food apply on top.

## 5. Radar and perception

- Each bot has independent **body heading, gun heading, radar heading** (Robocode's
  three-part tank). Gun and radar turn relative to the world, with optional
  `adjust_gun_for_body_turn` / `adjust_radar_for_gun_turn` flags (Robocode semantics).
- Each tick the radar sweeps the arc from last heading to new heading (≤ 45°). Every
  enemy body **inside that arc, within `radar_range`, and with LOS** produces a
  `ScannedBot` event: `bot_id, class_name, bearing, distance, heading, velocity,
  energy, elevation`. LOS reuses `VisibilityMgr.has_line_of_sight`, so hills and rock
  block radar, and stairs give vantage.
- In battle mode **radar is the only way to see other bots** *(decision)*. There's
  no 360° vision of bots; terrain stays visible within perception range so path
  planning still works.
- Events delivered in `BattleObservation`: `scanned_bots`, `hit_by_bullet`,
  `bullet_hit`, `bullet_missed`, `hit_wall`, `hit_bot`, `bot_death`, plus own state
  (x, y, headings, velocity, gun_heat, energy).

## 6. Bullets

- Spawn at the gun tip at muzzle height `cell_elevation + muzzle_height` (new
  `CreatureMoveProfile` field, default = `eye_height_offset`).
- Advance `speed` along the gun heading each tick; test the swept segment against
  every body circle (segment–circle test, not point test, so fast bullets can't skip
  through bots).
- **Terrain blocking:** the bullet stops when the cell it enters has elevation above
  its flight height, which is the same rule as LOS. Firing from stairs over a low
  rock works; firing into a hill doesn't. Bullets fly over water.
- Bullet–bullet collisions: off by default (Robocode has them; add later if wanted).
- Bullets leaving the arena → `bullet_missed`.

## 7. Rounds, scoring, results

Round ends when ≤ 1 team remains (a bot fighting alone is a team of one) or
`max_ticks_per_round` is reached.
Spawns are re-randomised each round (seeded). Bots are re-instantiated each round,
but a per-battle `memory` dict on the class is preserved, the equivalent of Robocode
static fields, so learning bots (GuessFactor stats) can carry data between rounds.

Scoring (Robocode-like, simplified):

| Component | Points |
|---|---|
| Survival | 50 per enemy that dies while you are alive |
| Last survivor | 10 × number of enemies at round start |
| Bullet damage | 1 per point of damage dealt |
| Bullet kill bonus | 20 % of damage dealt to a bot you killed |
| Ram damage | 2 per point; ram kill bonus 30 % |

Teams (built): leader +100 start energy, droids +20 and no radar, friendly fire
hurts but scores nothing (no energy back either), survival points only for enemy
deaths, last-survivor bonus per standing member of the last team, team places.
Team messages: `broadcast` / `send`, JSON data ≤ 4 KB, ≤ 10 per tick, delivered
next tick; unlimited range unless `team_message_range` is set (then range + LOS).
Battle files list teams as `[[teams]]` with `name` and `[[teams.members]]`; the
first member is the leader. Results add a team table (sum of members' scores).

Results table (per bot, sorted by total): rank, name, total score, survival, bullet
damage, ram damage, 1st/2nd/3rd places, hit rate (hits / shots), average energy at
death. Exported as CSV/JSON in headless mode (`results/<timestamp>.json`) for later
statistical analysis.

## 8. Running untrusted bots

Bots are arbitrary Python, and running someone else's bot means running their code.
For an educational platform:

- **v1** *(decision)*: bots run in-process. `decide()` is timed; exceeding
  `decide_time_budget_ms` skips that bot's turn (Robocode "skipped turns"). An
  exception in `decide()` is logged and counted as a skipped turn. Five consecutive
  exceptions disable the bot.
- **Later:** one subprocess per bot (multiprocessing pipes) for isolation and hard
  time limits. The `BattleObservation`/`BattleAction` dataclasses are already
  plain-data, so they serialise without redesign.
- Document clearly in the README: only run bots you trust.

## 9. Open decisions

Defaults above let work start. Confirm or change before or during implementation:

1. Hybrid continuous-on-grid (§2): yes / prefer pure grid?
2. `hit_energy_return` default `"damage"` (your rule) vs `"robocode"`.
3. Radar-only perception of bots in battle mode (§5).
4. Disabled-at-zero-energy rule (§4) vs instant death.
5. Teams: built (§7), with Robocode's leader/droid rules, friendly fire without
   points, and team messages of unlimited range by default.
6. Scoring weights (§7).

## 10. Protocol changes (viewer ⇄ server)

Today the socket is one-way (server → browser). Battle mode makes it bidirectional.

Client → server:
```json
{"type": "list_bots"}
{"type": "start_battle", "config": { ...BattleConfig... }, "bots": [{"spec": "bots.wanderer:WandererAgent", "count": 3}]}
{"type": "pause"} {"type": "resume"} {"type": "step"} {"type": "set_speed", "tick_delay_ms": 10}
{"type": "stop_battle"}
```
Server → client:
```json
{"type": "bot_list", "bots": [{"spec": "...", "name": "...", "doc": "first docstring line"}]}
{"type": "round_start", "round": 1, "world": { ...world_state... }}
{"type": "tick", "tick": 17, "bots": [{"id": 0, "x": 3.2, "y": 7.9, "heading": 90, "gun": 45, "radar": 10, "radar_prev": 325, "energy": 87.5, "gun_heat": 0.4, "state": "alive"}],
 "bullets": [{"id": 5, "x": 4.1, "y": 8.0, "z": 1.3, "power": 2.0}], "events": [{"type": "bullet_hit", "shooter": 0, "target": 2, "damage": 10.0}]}
{"type": "round_end", "round": 1, "scores": [...]}
{"type": "battle_end", "results": [...]}
```
- Bot discovery: scan `bots/*.py` and `terrabots/agents/*.py` for `BattleAgent` / `Agent`
  subclasses; `spec` = `module:Class`, same format as `terrabots-run --agent`.
- Send `world` only at `round_start`; switch terrain to flat arrays (elevation as a
  base64 Float32 buffer) instead of one dict per cell, which won't scale past ~64².

## 11. Viewer UI

Style: keep the flat-shaded low-poly terrain; dark UI chrome.

- **Setup screen** (overlay, shown on load / after battle): left, available bots
  with + / − counts; right, the settings form grouped as in §3 with tooltips showing
  the Robocode reference value; "Save as TOML" / "Load TOML"; Start.
- **Battle view:**
  - Bodies: Quaternius CC0 tank GLB (`https://poly.pizza/m/Dc4k4CooN3`), tinted per
    bot. **First check whether the GLB has a separate turret node.** If yes, rotate it
    with gun heading; if no, rotate the whole model by body heading and draw the gun
    as a thin box. Not verified yet.
  - Radar: translucent wedge from `radar_prev` to `radar` with radius
    `radar_range`, toggle per bot (click a bot) or for all ("R" key). Optional fading
    trail of the last N sweeps so you see what each bot has been watching.
  - Scan lines: brief line from scanner to each scanned bot on `ScannedBot`.
  - Bullets: small emissive spheres + short tracer; hit = flash, miss into terrain =
    puff.
  - Energy bar + name label above each bot; gun-heat indicator.
  - HUD: round x / N, tick, scoreboard (live), controls: pause / step / speed slider
    / camera follow bot / top-down toggle.
- **Results dialog** after the last round, the table from §7, with "Run again" and
  "Back to setup".
- Upgrade Three.js from r128 → a current release when touching the viewer
  (r152+ renamed `outputEncoding` → `outputColorSpace`; `GLTFLoader` import path
  `three/addons/loaders/GLTFLoader.js`). Pin an exact version in the import map.

## 12. Suggested implementation order

Each step ends green (`pytest`) and is committed separately.

1. `BattleConfig` + TOML load/validate + tests.
2. Kinematics: `BattleBody` (float pos, three headings, velocity, accel/turn limits,
   cell-crossing passability) + tests incl. climb limit across a cell boundary.
3. Radar sweep arc + LOS gating + `ScannedBot` events + tests (bot behind rock not
   scanned, bot on stairs scanned).
4. Bullets: spawn, swept-segment hit test, terrain blocking, gun heat, energy
   economics (all three `hit_energy_return` modes) + tests.
5. `BattleRunner`: rounds, respawn, scoring, results JSON, decide() time budget,
   seeded determinism test (same seed → identical results).
6. CLI: `terrabots-battle battles/example.toml [--headless] [--rounds N]`, plus a
   VS Code launch config.
7. Server: bidirectional protocol, bot discovery, pause/step/speed.
8. Viewer: setup screen → battle view → radar/bullets → results dialog → GLB tanks.
9. Example bots: `SittingDuck`, `SpinBot` (radar spin + fire), `Tracker`
   (lock radar, head-on targeting). Then a real **MuBot battle port** (in the private mubot repo, not here) (anti-gravity
   movement + GuessFactor targeting), which maps far more directly to battle mode
   than the survival-mode conceptual port does. For a faithful port, put the
   original Java MuBot source in `reference/mubot/` first.
