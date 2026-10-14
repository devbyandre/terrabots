# Robocode bots in Terrabots

Terrabots follows Robocode's rules, so Robocode bots can fight here unchanged:
the [Robocode adapter](../adapters/robocode/) runs a bot's `.jar` in a Java
sandbox container and translates between Robocode's API and the engine.

```bash
docker build -t terrabots-sandbox-robocode -f docker/sandbox-robocode.Dockerfile adapters/robocode/
terrabots-battle --headless --jar path/to/SomeBot.jar --bot terrabots.agents.crazy:Crazy
```

From Python:

```python
from terrabots.battle import BattleConfig, BattleRunner
from terrabots.battle.sandbox import JarEntry

bot, = JarEntry.from_jar("SomeBot.jar")[:1]      # reads robot.classname from the jar
config = BattleConfig(rounds=10, terrain="flat", width=50, height=37, hit_energy_return="robocode")
print(BattleRunner(config, [(bot, 1), (MyTank, 1)]).run().table())
```

`width=50, height=37` is Robocode's 800 × 600 px field as closely as whole cells
allow (800 × 592 px at 16 px per cell). Don't make it larger than the field a bot
expects: many 1v1 bots hard-code 800 × 600, and some loop forever outside it,
and `hit_energy_return="robocode"` gives the shooter 3 × power back on a hit, as
in Robocode.

## What works

- `Robot` (blocking commands), `AdvancedRobot` (queued commands, custom events,
  `waitFor`, data files), `TeamRobot` (messages: Java objects, serialized),
  `RateControlRobot`, droids (`robocode.Droid`), and bots built directly on
  `robocode.robotinterfaces` and the peer API.
- Robocode's semantics that strong bots rely on: one robot peer for the whole
  battle (objects from earlier rounds keep working), time starting at 0 with a
  status event before `run()`, event order and priorities, bullet positions at
  the end of the tick (speed × ticks flown from where they were fired), static
  fields surviving the rounds; a crashing bot stands still for the rest of the
  round, and one that hangs gets a fresh container for the next round.

How close is it? `tools/robocode_conformance/conformance.py` runs a probe bot in
real Robocode 1.11 and in Terrabots from the same start and diffs what it logs
every turn (position, headings, velocity, energy, gun heat, scans, bullet
events): 0 differences over a whole round. Fights between two bots match until
two bullets resolve in the same turn, which Robocode does in random order.

A mini-rumble of 24 RoboRumble bots spread over the whole
ranking (rank 1 to 1151), every pair 1v1 on the 800 × 592 field, 10 rounds each:
the ranking correlates 0.97 (Spearman) with the official RoboRumble ranking, and
most bots score within a few points of their official APS.
- On terrain maps the bots play too, but they don't know about hills: they can
  lose sight of you behind a hill and their bullets can hit the ground.

## What doesn't (yet)

- `JuniorRobot`, team `.team` files.
- A few bots still misbehave; one obfuscated top bot, for example, aims about 90°
  off its target, for reasons not found yet.
- Drawing (`onPaint`) and bot colours aren't shown in the viewer.
- Java bots use `Math.random()`, which can't be seeded from outside, so their
  battles aren't exactly repeatable.
- `setAdjustRadarForRobotTurn` is approximated.

## Licences

Running a bot you downloaded is using it. Copying or porting its code is
different: RoboRumble bots carry their authors' licences (often the RoboWiki
Public Code License, which asks that derived code be published under the same
terms, or none at all). Terrabots ships no Robocode bots, and the tournament
only includes bots whose authors submitted them.
