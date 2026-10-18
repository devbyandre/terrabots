# Changelog

## Unreleased

### Added
- Persistent bot storage (`self.storage`, `bot_data/`, 200 KB quota per bot class).
- Demo bots: Walls, RamFire, Corners, Learner (battle), Grazer (survival).
- Viewer: survival mode in the setup screen, fog of war (F), per-tank radar
  toggles, bot colours (`set_colors`).
- Maps: JSON map files, seven built-in maps, map selection for battles and
  survival runs, an in-browser map builder with a playability check.
- Smooth terrain rendering (G toggles the game cells), bot consoles (C) for
  your own bots' prints, `self.log()` and logs.
- Teams: `[[teams]]` in battle files and a team picker in the setup screen;
  leaders (+100 energy), droids (+20, no radar), team messages
  (`broadcast`/`send`, optional range + line of sight), friendly fire without
  points, team scoring and a team results table. `TeamRobot` and `Droid` for
  ported Robocode bots. Demo team: `SquadLeader` + `SquadDroid`.
- Tournament and leaderboard (`tools/tournament.py`), bot submissions in
  `contrib/`, Jupyter notebooks, an animated battle in the README.

- Sandbox for other people's bots (`terrabots.battle.sandbox`, docs/sandbox.md):
  a Docker container per bot without network or access to your files, a checked
  JSON protocol, no host imports. Used for `contrib/` and `submissions/` in the
  tournament and the setup screen, and by `terrabots-battle --headless --sandbox`.
- Private bot submissions (the default): only name, author and scores are
  published. `tools/tournament.py --extra SPEC@AUTHOR` adds your own closed-source
  bots.

- Robocode adapter (`adapters/robocode`, docs/robocode-bots.md): Robocode jar bots
  run unchanged in a Java sandbox container; `terrabots-battle --headless --jar`.
- Offline tournament tools (`tools/airgap`, docs/airgap.md).
- `tools/robocode_conformance/`: runs a probe bot in real Robocode and in Terrabots
  and diffs their per-tick logs.

### Changed
- Battle physics now follow Robocode exactly where a probe found differences: guns
  fire before bullets move and cool after (a new bullet takes its first step in
  the tick it's fired, and the queued shot no longer lets a bot fire a tick
  early); bullets resolve one by one in random order, the arena edge (within the
  3 px bullet radius) before tanks, the first tank touched rather than the nearest;
  the radar meets the tank's square box; inactivity drains from the 452nd quiet
  tick and disables a tank at 0 before it dies. Results of seeded battles change.
- The radar only scans when the tank moved or turned something that tick, or
  asked for a scan (`BattleAction.scan`, `AdvancedRobot.scan()`), as in Robocode.
- Robocode adapter: turns are counted in radians with Robocode's own arithmetic
  (a turn can end a tick later than the degrees suggest, and bots notice);
  `scan()` interrupts a running `onScannedRobot`; `isTeammate` is true for the
  bot's own name; `setAdjustRadarForGunTurn` also sets the body-turn adjustment
  unless the bot set that itself; blocking calls (`ahead`, `turnGunRight`, ...)
  always take at least one turn.
- Robocode rules for plain `Robot`s (`BattleAgent.plain_robot`): no wall damage,
  and fire assistance (a shot fired from this turn's `onScannedRobot` with gun and
  radar aligned flies straight at the scanned robot; `BattleAction.fire_heading`,
  checked by the engine).
- A tank that hits a wall ends its move touching it, not where it started the tick.
- Two bullets flying along the same line pass each other, as in Robocode (only
  crossing paths collide).
- The tournament workflow only checks pull requests (sandboxed, read-only); the
  leaderboard is built by the maintainer, where private submissions are.
- Process isolation sends the terrain after the bot has started, so a bot that
  fails to start reports an error instead of hanging the battle.
- Results CSV/JSON have a `team` column (last, so existing scripts keep working).
- Bot names are numbered when a class appears more than once in a battle, also
  across teams. Classes whose names start with `_` aren't listed as bots.

## 0.3.0 — 2026-10-12

### Added
- Bots in their own processes (`bot_isolation = "process"`): parallel turns,
  hard time limit, crash containment.
- `terrabots.battle.robocode.AdvancedRobot`: Robocode's queued-command API for
  porting Java bots.
- Graphical debugging (`self.draw`, viewer key D), battle rules for bots
  (`self.rules`), bullet ids in events (`bullet_fired`, `bullet_hit_bullet`).
- Docker: `docker compose up` runs the battle and survival viewers.

### Changed (checked against RoboWiki's Robocode pages)
- Bullets move before robots; bodies are 36 px squares; crossing bullets
  collide; a bot moving away from contact isn't stopped; inactivity drain after
  450 quiet ticks; kill bonuses are a share of all damage to the victim; braking
  through zero accelerates for the rest of the tick.
- Radar range defaults to Robocode's 1200 px (75 cells).
- Survival: visible terrain is cached per cell.

## 0.2.0 — 2026-10-12

### Added
- **Battle mode** (`terrabots-battle`): Robocode-style tanks with independent
  body, gun and radar headings; radar sweeps gated by elevation-aware line of
  sight; bullets that terrain can block; energy economics with three hit-return
  modes; rounds and Robocode-like scoring; results as JSON/CSV.
- Battle viewer: setup screen (bot discovery, every rule, TOML load/save), live
  3D battle view, results dialog.
- Demo bots: `SittingDuck`, `SpinBot`, `Tracker`, `Crazy`; template
  `bots/first_tank.py`.
- `BattleConfig` and TOML battle files (`battles/example.toml`).
- Survival food respawn (`ResourceConfig.spawn_rate`).
- CI on Python 3.11–3.13.

### Changed
- Project renamed from BioBot to Terrabots.
- Viewers upgraded from Three.js r128 to 0.186.1.
- Procedural terrain moved to `terrabots/map_generator.py`.
- Test scenarios split into individual pytest functions.

## 0.1.0

- Survival mode: 2.5D terrain, elevation-aware LOS, comms, viewer.
