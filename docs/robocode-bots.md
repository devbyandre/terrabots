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
  `RateControlRobot`, droids (`robocode.Droid`).
- Event order and priorities as in Robocode; static fields survive the rounds of
  a battle; a crashing bot stands still for the rest of the round.
- On terrain maps the bots play too, but they don't know about hills: they can
  lose sight of you behind a hill and their bullets can hit the ground.

## What doesn't (yet)

- Bots built on `robocode.robotinterfaces` without extending `robocode.Robot`,
  `JuniorRobot`, team `.team` files.
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
