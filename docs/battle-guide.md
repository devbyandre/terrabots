# Battle guide: rules, physics and strategies

This guide explains how a Terrabots battle works and how good bots play it, from
your first tank to learning guns. Terrabots follows the rules of
[Robocode](https://robocode.sourceforge.io/), so most of what the Robocode community
worked out over twenty years applies directly; the
[RoboWiki](https://robowiki.net/) is the deep reference and is linked throughout.
What Terrabots adds is terrain, and the last part of the guide is about that.

Numbers below are the defaults of [`BattleConfig`](../terrabots/battle/config.py).
Every one of them can be changed in the setup screen or a battle file.

---

## 1. Units and directions

- **Distance**: cells. One cell is 16 Robocode pixels, so Robocode numbers convert
  by dividing by 16 (a 36 px tank is 2.25 cells wide).
- **Time**: ticks. Every bot gets one decision per tick.
- **Headings**: degrees, 0 = north, 90 = east, clockwise, exactly as in Robocode
  ([Game physics](https://robowiki.net/wiki/Robocode/Game_Physics)). The point
  `distance` away along `heading` is `x + sin(heading) * distance`,
  `y + cos(heading) * distance` (note: sin for x, cos for y, the opposite of school
  maths). `terrabots.battle.geometry` has helpers for all of this.
- A **bearing** is the heading from you to something. Events from the
  `AdvancedRobot` API give it relative to your body, `ScannedBot` gives it absolute.

## 2. What happens in one tick

1. Every bot gets its observation and decides. All bots decide on the same
   state, nobody sees the others' moves of this tick.
2. **Bullets move**, including the ones fired last tick, and hit tanks, each other
   or terrain.
3. **Guns cool down, then fire.** A bullet leaves along the gun heading *before*
   this tick's gun turn. (Turn the gun this tick, fire next tick.)
4. **Gun, radar and body turn.**
5. **Tanks accelerate and move**; walls, terrain and other tanks stop them.
6. **Radars sweep** and produce `scanned_bots` for the next tick.

Events from a tick (hits, scans, deaths) arrive in your next observation.

## 3. Physics

| Rule | Value | Robocode |
|---|---|---|
| Tank | 2.25 × 2.25 cell square, doesn't rotate with the heading | 36 × 36 px |
| Max speed | 0.5 cells/tick | 8 px/tick |
| Acceleration / braking | 1/16 / 2/16 cells/tick² | 1 / 2 px/tick² |
| Body turn | 10° − 0.75° × speed in px/tick (10° standing, 4° at full speed) | same |
| Gun turn / radar turn | 20° / 45° per tick, added on top of the body's turn unless you set `adjust_*` | same |
| Bullet power | 0.1 to 3.0 | same |
| Bullet speed | (20 − 3 × power) / 16 cells/tick: 1.23 at power 0.1, 0.69 at 3 | 20 − 3p px/tick |
| Damage | 4 × power, plus 2 × (power − 1) above power 1 (16 at power 3) | same |
| Firing cost | the power, immediately | same |
| Energy back on a hit | the damage dealt (Terrabots default) | 3 × power |
| Gun heat | +1 + power/5 per shot, cools 0.1/tick, no firing while hot, starts at 3 | same |
| Radar | 75 cells, needs line of sight | 1200 px, no terrain |
| Wall hit | stops the tank, damage = speed in px/tick × 0.5 − 1 (max 3) | same |
| Ramming | 0.6 damage to both; a tank driving *away* isn't stopped | same |
| Bullets crossing | both vanish | same |
| Inactivity | after 450 ticks without any damage, everyone loses 0.1 energy/tick | same |
| Zero energy | disabled (can't move or fire), destroyed by the next damage | same |

**Two numbers worth remembering:**

- **Bullet flight time** = distance / bullet speed. At 15 cells a power-3 bullet
  needs 22 ticks; in that time a tank can move 11 cells. That's why aiming at
  where the enemy *is* misses moving targets.
- **Maximum escape angle** = asin(max speed / bullet speed): the furthest
  sideways a target can get, seen from the shooter, before a bullet arrives. At
  power 2 it's about 35°. It's the yardstick for guess factors (section 6).
  ([Maximum Escape Angle](https://robowiki.net/wiki/Maximum_Escape_Angle))

## 4. Scoring

Exactly Robocode's ([Scoring](https://robowiki.net/wiki/Robocode/Scoring)):

| What | Points |
|---|---|
| Survival | 50 every time another bot dies while you're alive |
| Last survivor | 10 per bot that died before you |
| Bullet damage | 1 per point of damage |
| Bullet kill bonus | 20 % of all the damage you did to a bot you killed |
| Ram damage | 2 per point of damage |
| Ram kill bonus | 30 % of all the damage you did to a bot you rammed dead |

1sts, 2nds and 3rds only show placings; they don't add points. Survival points
are often the biggest share, so **staying alive is worth as much as hitting**.

## 5. Energy management

Energy is both your health and your ammunition.
([Energy Management](https://robowiki.net/wiki/Energy_Management))

- A shot of power p costs p. With the default rule a hit returns the damage
  dealt, so for p ≤ 1 a hit returns 4p: **a shot pays for itself if more than a
  quarter of them hit** (a third under Robocode's 3p rule). Strong shots pay off
  up close, weak ones at long range.
- Don't waste power on a finishing shot: the damage needed to kill is the
  target's energy; pick the smallest power that deals it.
- Low on energy? Shooting badly makes it worse. Fire only shots you expect to
  hit, or none; in a melee, let the others fight and collect survival points.

## 6. Strategies, step by step

Each level builds on the one before. The demo bots in
[`terrabots/agents/`](../terrabots/agents/) are short, readable examples.

### Level 1: radar

You only know about enemies your radar sweeps. ([Radar](https://robowiki.net/wiki/Radar))

- **Spin** (`radar_turn=45` every tick): sees everything eventually. *SpinBot.*
- **Lock** (1v1): turn the radar to the enemy's bearing and a bit beyond
  (about 2 × the difference); every tick's sweep crosses the target again.
  ([One on One Radar](https://robowiki.net/wiki/One_on_One_Radar)) *Tracker.*
- **Melee**: sweep back and forth just past the outermost enemies, so every
  enemy is refreshed often. ([Melee Radar](https://robowiki.net/wiki/Melee_Radar))
- Set `adjust_gun_for_body_turn` / `adjust_radar_for_gun_turn` so body, gun and
  radar turn independently; it makes everything above simpler.

### Level 2: aiming

- **Head-on**: aim at the enemy's current position. Hits standing and slow bots.
  ([Head-On Targeting](https://robowiki.net/wiki/Head-On_Targeting))
- **Linear**: assume it keeps heading and speed; aim where it will be when the
  bullet arrives. Solve it by iterating: guess the flight time, predict the
  position, recompute the flight time. *Crazy.*
  ([Linear Targeting](https://robowiki.net/wiki/Linear_Targeting))
- **Circular**: like linear, but also keep its turn rate. Hits bots driving in
  arcs. ([Circular Targeting](https://robowiki.net/wiki/Circular_Targeting))
- Fire only when the gun is cool *and* already pointing where you want
  (gun turns take ticks).

### Level 3: movement

Not being hit is worth as much as hitting.

- **Perpendicular movement**: drive at right angles to the line to your enemy;
  that's where its bullets need the most lead. Reverse now and then.
  ([Oscillator Movement](https://robowiki.net/wiki/Oscillator_Movement))
- **Random / stop-and-go**: unpredictable speed and direction changes defeat
  linear and circular guns. ([Random Movement](https://robowiki.net/wiki/Random_Movement),
  [Stop And Go](https://robowiki.net/wiki/Stop_And_Go))
- **Wall smoothing**: before you drive, check that the next few cells are clear
  and bend your heading if not; every wall hit costs energy and leaves you
  standing still. ([Wall Smoothing](https://robowiki.net/wiki/Wall_Smoothing))
- **Anti-gravity** (melee): every enemy pushes you away, walls push you off, you
  move along the sum of the forces. Simple and effective, but forces can cancel
  out and leave you parked. ([Anti-Gravity Movement](https://robowiki.net/wiki/Anti-Gravity_Movement))
- **Minimum risk movement** (melee): look at a ring of points around you, give
  each a risk (enemy energy ÷ distance², being cornered, staying put) and drive
  to the safest. Usually better than anti-gravity because nothing cancels out.
  ([Minimum Risk Movement](https://robowiki.net/wiki/Minimum_Risk_Movement))

### Level 4: waves

A bot can't see bullets, but it can see that an enemy's energy just dropped by
0.1 to 3: it fired, and the drop is the power. From that moment the bullet is
somewhere on a circle (a **wave**) growing from where the enemy stood, at the
known bullet speed. ([Waves](https://robowiki.net/wiki/Waves))

- **Dodging**: change direction when a wave is fired; guns that aim where you
  were heading miss.
- Subtract energy changes you can explain before deciding it fired: your hits
  on it, its hits on you (it gets energy back), rams, wall hits (a sudden stop),
  and ignore drops while its gun can't be cool yet.
- **Wave surfing**: remember where on earlier waves you were hit, and move to
  the part of the current wave that has been safest. The strongest 1v1
  movement there is. ([Wave Surfing](https://robowiki.net/wiki/Wave_Surfing),
  [Wave Surfing Tutorial](https://robowiki.net/wiki/Wave_Surfing_Tutorial))

### Level 5: learning

- **GuessFactor targeting**: send your own waves at the enemy every tick. When
  one reaches it, record where it ended up as a fraction of the maximum escape
  angle in its sideways direction (−1 … +1). Over time a histogram shows where
  this enemy tends to be; aim at the peak. *Learner* is a compact example.
  ([GuessFactor](https://robowiki.net/wiki/GuessFactor),
  [GuessFactor Targeting Tutorial](https://robowiki.net/wiki/GuessFactor_Targeting_Tutorial))
- **Segmentation**: keep separate histograms per situation (distance, sideways
  speed, near a wall...), because a bot behaves differently in each.
  ([Segmentation](https://robowiki.net/wiki/Segmentation))
- **Virtual guns**: fire every gun you have virtually on every wave, count which
  would have hit, and shoot with the best one *against this opponent*. No gun
  wins everywhere: circular is best against circling bots, guess factors against
  random movers. ([Virtual Guns](https://robowiki.net/wiki/Virtual_Guns))
- **Pattern matching**: find the moment in the enemy's movement history that
  looks most like now and replay what happened next.
  ([Pattern Matching](https://robowiki.net/wiki/Pattern_Matching))
- **Remember between battles** with `self.storage` (200 KB per bot class).
  *Corners* and *Learner* do.
- **Choosing strategies**: if several strategies are close, a multi-armed bandit
  (e.g. UCB, Auer et al. 2002) can learn per opponent which one scores best.
  Beware: survival points depend on when the others die, so compare whole rounds,
  not short stretches, or the bandit learns from luck.

## 7. Terrain: what Terrabots adds

Everything above works on a flat map. On terrain:

- **Line of sight** is elevation only: a cell blocks the view if it rises above
  the straight line from the observer's eye (ground + 1) to the target's ground.
  Radar and messages need it. Hide behind a hill and nobody scans you.
- **Bullets fly level** at the shooter's muzzle height (ground + 1). Ground that
  rises above that stops them. From high ground you shoot over low cover; from a
  valley you hit the hillside. Check the path before firing.
- **Climbing** more than 2 height units in one step is impossible; deep water and
  rock are impassable. The whole 2.25-cell square must fit, so a single rock
  under the edge of the tank stops it.
- **You only see terrain within 15 cells**; it never changes, so remember what
  you've seen (the battlefield is the same in every round of a battle).

Strategies that follow:

- **Cover instead of corners**: a corner is safe because attacks come from few
  directions; a pocket behind a hill is too. Rate cells by how many directions
  are blocked by edges or high ground.
- **Exposure**: in a melee, prefer positions where only your target can see you.
- **Search**: if nobody is in radar view, the enemies are hiding behind terrain;
  climb for a better view instead of standing still.
- **Wave shadows**: an enemy's bullet can't reach a point that terrain shields
  from its muzzle height, so those points are safe from that wave.

## 8. Teams

Robocode's team rules (from general knowledge of Robocode; the RoboWiki pages
above don't cover them in detail):

| What | Rule |
|---|---|
| Leader | the team's first member; starts with 200 energy (`team_leader_bonus` +100) |
| Droid | `droid = True` on the class: 120 energy (`droid_bonus` +20), **no radar** |
| Friendly fire | bullets and rams hurt teammates but score nothing and give no energy back |
| Scans | teammates show up in `scanned_bots` with `teammate=True` |
| Messages | `self.broadcast(data)` / `self.send(to, data)`; teammates read them next tick in `obs.team_messages` |
| Message range | anywhere by default (Robocode); set `team_message_range` and they need range and line of sight, so hills cut the radio |
| Round end | when only one team is left |
| Scoring | survival points only for enemy deaths; last-survivor bonus to every standing member of the last team; places are team places; a team's score is the sum of its members' |

Messages are plain data (dicts, lists, strings, numbers), at most 4 KB each and
10 per tick. Ported Robocode team bots use `TeamRobot` (`broadcast_message`,
`send_message`, `on_message_received`) and mix in `Droid`.

Strategies, in the order teams usually learn them:

- **Don't shoot each other.** Share your position every tick and hold fire when
  a teammate is near the line of fire. Friendly fire is the first thing that
  beats a new team: `Tracker` doesn't know about teams, and in
  `battles/teams.toml` about a third of the Trackers' bullet damage (672 of
  2175 over the 10 rounds) hits their own teammates. The team of three finishes
  behind both bots that fight alone.
- **Share what you see.** One radar can serve the whole team. In
  [`squad.py`](../terrabots/agents/squad.py) the leader spins its radar and
  broadcasts every enemy; its droids have no radar at all and still hit,
  because they aim at the reports (with linear targeting from the report's age).
- **Pick one target.** Two bots firing at the same enemy kill it in half the
  time, and a dead enemy stops scoring and shooting. Let the leader name the
  target.
- **Spread out.** Enemy bullets aimed at one teammate hit the one standing next
  to it; on terrain, a teammate on high ground can see (and report) what the
  others can't.
- **Protect the leader.** It has the most energy, and with droids on the team
  it's also the only one that can see.

## 9. Measuring what works

Feelings lie; seeded battles don't.

```bash
terrabots-battle --headless --rounds 60 --seed 1 --bot bots.my_tank:MyTank \
    --bot terrabots.agents.tracker:Tracker --bot terrabots.agents.crazy:Crazy
```

- Change one thing at a time and compare on the same seeds.
- Use many rounds (60+) and more than one seed batch: differences of 10 % between
  two runs of the same bot are normal.
- Test against several opponents and on flat and hilly terrain; an improvement
  against one can be a loss against another.
- `results/*.csv` loads straight into pandas or a spreadsheet.

## References

- Robocode: https://robocode.sourceforge.io/ · RoboWiki: https://robowiki.net/
- Auer, P., Cesa-Bianchi, N., & Fischer, P. (2002). Finite-time analysis of the
  multiarmed bandit problem. *Machine Learning*, 47, 235–256.
- Hansen, N., & Ostermeier, A. (2001). Completely derandomized self-adaptation in
  evolution strategies. *Evolutionary Computation*, 9(2), 159–195. (CMA-ES, for
  tuning a bot's parameters offline.)
