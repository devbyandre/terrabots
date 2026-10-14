"""
Arena: runs one battle round, tick by tick.

Tick order follows Robocode's processing loop (RoboWiki: Robocode/Game_Physics),
with all bots deciding on the same pre-tick state as in survival mode:
  1. Build each bot's observation (its state + events from last tick) and call decide()
  2. Fire: guns at heat 0 shoot along the gun heading *before* this tick's turn,
     from where the bot stands before it moves
  3. Move bullets, the new ones included (a bullet makes its first step in the
     tick it's fired); resolve hits on bodies, bullet-bullet collisions, terrain
     and arena misses
  3b. Cool guns
  4. Turn gun, radar and body
  5. Accelerate and move bodies; resolve terrain/arena walls and rams
  6. Radar sweeps -> ScannedBot events
  7. Inactivity drain, deaths, scoring, comms delivery
Events produced in steps 2-7 reach bots in the next tick's observation.
The order of 2-3b, the inactivity timing and the radar's square bodies were
checked against Robocode 1.11 with a probe bot logging every tick in both engines.

Teams: each bot has a team (agent.team; None = alone). The round ends when only
one team is standing. Friendly fire hurts but scores nothing (see scoring.py).
Team messages (agent.broadcast/send) are collected after decide() and delivered
with the comms in step 7, so they are read next tick; with team_message_range
set they also need range and line of sight. Droids have no radar.

decide() is timed. A turn that runs over decide_time_budget_ms, or raises, is
skipped: the bot keeps its target speed but doesn't turn or fire (Robocode's
"skipped turns"). Five consecutive exceptions and the bot is switched off for the
round. A bot can run in its own process (see terrabots.battle.isolation); the
arena doesn't care, it only calls the BattleAgent methods.
"""

from __future__ import annotations

import dataclasses
import logging
import math
import random
import time
from typing import Any

from terrabots.battle.actions import BattleAction
from terrabots.battle.agent import BattleAgent
from terrabots.battle.config import BattleConfig
from terrabots.battle.events import (
    BotDeath,
    BulletFired,
    BulletHit,
    BulletHitBullet,
    BulletMissed,
    HitBot,
    HitByBullet,
    HitWall,
    ScannedBot,
    TeamMessage,
)
from terrabots.battle.geometry import clamp, distance, heading_to, normalize_heading
from terrabots.battle.isolation import BotProcessError, RemoteBot
from terrabots.battle.observation import BattleObservation, TerrainView
from terrabots.battle.physics import (
    ALIVE,
    DEAD,
    DISABLED,
    BattleBody,
    Bullet,
    apply_turns,
    blocked_reason,
    boxes_overlap,
    bullet_next,
    footprint_passable,
    in_radar_arc,
    next_velocity,
    segment_box_t,
    segments_intersect_t,
    terrain_block_t,
)
from terrabots.battle.scoring import BotScore, RoundScorer
from terrabots.comms import CommsMgr, MessageType
from terrabots.console import capture
from terrabots.world_terrain import MovementResolver, VisibilityMgr, WorldGrid

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_ERRORS = 5
MIN_SPAWN_SEPARATION = 6.0  # cells between spawned bodies (centres)

EVENT_KINDS = ("scanned_bots", "hit_by_bullet", "bullet_hit", "bullet_missed", "bullet_fired",
               "bullet_hit_bullet", "hit_wall", "hit_bot", "bot_death")


class _Slot:
    """Arena-side bookkeeping for one bot."""

    def __init__(self, agent: BattleAgent, body: BattleBody, scan_profile: Any) -> None:
        self.agent = agent
        self.body = body
        self.scan_profile = scan_profile       # profile with perception = radar range
        self.events: dict[str, list] = _empty_events()
        self.last_velocity_cmd = 0.0
        self.consecutive_errors = 0
        self.skipped_turns = 0
        self.switched_off = False
        self.killer: int | None = None         # last bot that damaged us
        self.killed_by_ram = False
        self.drawings: list[dict[str, Any]] = []
        self.console: list[str] = []
        self.team_inbox: list[TeamMessage] = []   # delivered last tick, read this tick


def _empty_events() -> dict[str, list]:
    return {k: [] for k in EVENT_KINDS}


class Arena:
    def __init__(self, config: BattleConfig, world: WorldGrid, agents: list[BattleAgent],
                 round_number: int, rng: random.Random,
                 time_budget_ms: float | None = None, console_ids: set[int] | None = None) -> None:
        self.cfg = config
        self.world = world
        self.round = round_number
        self.tick = 0
        self.time_budget_ms = time_budget_ms
        self.console_ids = console_ids or set()      # bots whose prints/logs go to the viewer
        self._movement = MovementResolver(world)
        self._visibility = VisibilityMgr(world)
        self._comms = CommsMgr(self._visibility)
        self._bullets: list[Bullet] = []
        self._rng = rng                                  # also Robocode's random bullet/robot order
        self._next_bullet_id = 0
        self._frame_events: list[dict[str, Any]] = []
        self._ticks_since_damage = 0
        self._outgoing: list[tuple[int, int | None, object]] = []   # (sender, recipient, data)

        self.slots: dict[int, _Slot] = {}
        for agent in agents:
            x, y = self._spawn_point(agent, rng)
            heading = rng.uniform(0, 360)
            energy = (config.initial_energy + (config.team_leader_bonus if agent.is_leader else 0.0)
                      + (config.droid_bonus if agent.droid else 0.0))
            body = BattleBody(agent.bot_id, x, y, heading=heading, gun_heading=heading,
                              radar_heading=heading, radar_prev=heading,
                              energy=energy, gun_heat=config.initial_gun_heat)
            scan_profile = dataclasses.replace(agent.profile, max_perception_range=config.radar_range)
            self.slots[agent.bot_id] = _Slot(agent, body, scan_profile)

        self.scorer = RoundScorer(
            {bid: BotScore(s.agent.name, _class_name(s.agent)) for bid, s in self.slots.items()},
            teams={bid: s.agent.team for bid, s in self.slots.items() if s.agent.team is not None})

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _spawn_point(self, agent: BattleAgent, rng: random.Random) -> tuple[float, float]:
        half = self.cfg.body_half_width
        taken = [(s.body.x, s.body.y) for s in self.slots.values()]
        for attempt in range(20_000):
            # Relax the separation rule on crowded maps instead of failing.
            sep = MIN_SPAWN_SEPARATION if attempt < 10_000 else 2 * half + 0.1
            x = rng.uniform(half, self.world.width - half)
            y = rng.uniform(half, self.world.height - half)
            if not footprint_passable(x, y, self.world, self._movement, agent.profile, half):
                continue
            if all(distance(x, y, ox, oy) >= sep for ox, oy in taken):
                return x, y
        raise RuntimeError("No room to spawn all bots; use a larger arena or fewer bots")

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def standing(self) -> list[_Slot]:
        """Bots not destroyed (alive or disabled)."""
        return [s for s in self.slots.values() if s.body.state != DEAD]

    def teams_standing(self) -> set:
        return {self.scorer.team_of(s.body.bot_id) for s in self.standing()}

    @property
    def over(self) -> bool:
        return len(self.teams_standing()) <= 1 or self.tick >= self.cfg.max_ticks_per_round

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def step(self) -> dict[str, Any]:
        """Advance one tick. Returns a viewer frame (see docs/arena-spec.md §10)."""
        self.tick += 1
        self._frame_events = []
        standing = self.standing()

        actions = self._decide_all(standing)
        for s in standing:
            s.events = _empty_events()
        self._comms.clear()

        for s in standing:
            self._fire(s, actions[s.body.bot_id])
        self._move_bullets()
        for s in standing:
            s.body.gun_heat = max(0.0, s.body.gun_heat - self.cfg.gun_cooling_rate)
        for s in standing:
            a = actions[s.body.bot_id]
            if s.body.state == ALIVE:
                apply_turns(s.body, a.body_turn, a.gun_turn, a.radar_turn, self.cfg,
                            s.agent.adjust_gun_for_body_turn, s.agent.adjust_radar_for_gun_turn)
            else:
                s.body.radar_prev, s.body.radar_sweep = s.body.radar_heading, 0.0
        for s in standing:
            self._move(s, actions[s.body.bot_id])
        for s in standing:
            if s.body.state == ALIVE:
                if not s.agent.droid:
                    self._radar_sweep(s)
                if actions[s.body.bot_id].shout is not None:
                    self._shout(s, actions[s.body.bot_id])
        self._inactivity()
        self._resolve_deaths()
        self._comms.deliver()
        self._deliver_team_messages()
        return self.frame()

    # ------------------------------------------------------------------

    def _skip(self, s: _Slot) -> BattleAction:
        s.skipped_turns += 1
        self.scorer.scores[s.body.bot_id].skipped_turns += 1
        return BattleAction(velocity=s.last_velocity_cmd)

    def _decide_all(self, standing: list[_Slot]) -> dict[int, BattleAction]:
        """Ask every active bot for its action. Bots in their own process all get
        their observation first and think in parallel; then answers are collected."""
        # Disabled bots (0 energy) keep running their code, as in Robocode; the arena
        # ignores what they ask for.
        active = [s for s in standing if s.body.state in (ALIVE, DISABLED) and not s.switched_off]
        self._skipped_before = {s.body.bot_id: s.skipped_turns for s in active}
        for s in standing:
            s.drawings = []
            s.console = []
        remote = [s for s in active if isinstance(s.agent, RemoteBot)]
        for s in remote:
            s.agent.request_decide(self._observe(s))
        actions = {s.body.bot_id: BattleAction() for s in standing}
        for s in active:
            actions[s.body.bot_id] = self._decide(s, remote=s in remote)
        self._outgoing = []
        for s in active:
            # Messages of a skipped turn are dropped along with its action.
            sent = s.agent.take_outbox()
            if s.skipped_turns == self._skipped_before[s.body.bot_id]:
                self._outgoing += [(s.body.bot_id, to, data) for to, data in sent]
        for s in standing:
            s.team_inbox = []
        return actions

    def _decide(self, s: _Slot, remote: bool = False) -> BattleAction:
        start = time.perf_counter()
        try:
            if remote:
                action = s.agent.collect_decide(self.time_budget_ms)
                elapsed_ms = s.agent.last_elapsed_ms     # measured in the bot's process
                s.console = list(s.agent.last_console)
            else:
                obs = self._observe(s)
                s.agent.draw.clear()
                with capture(s.agent, s.body.bot_id in self.console_ids) as lines:
                    action = s.agent.decide(obs)
                s.console = lines
                elapsed_ms = (time.perf_counter() - start) * 1000
            if not isinstance(action, BattleAction):
                raise TypeError(f"decide() returned {type(action).__name__}, expected BattleAction")
        except BotProcessError as exc:
            # A crashed or killed process won't come back this battle.
            if s.agent.is_dead:
                s.switched_off = True
            s.consecutive_errors += 1
            logger.warning("%s: %s", s.agent.name, exc)
            if s.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                s.switched_off = True
            return self._skip(s)
        except Exception:
            s.consecutive_errors += 1
            logger.warning("%s raised in decide() (round %d, tick %d)", s.agent.name,
                           self.round, self.tick, exc_info=s.consecutive_errors == 1)
            if s.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                s.switched_off = True
                logger.warning("%s switched off after %d consecutive errors",
                               s.agent.name, MAX_CONSECUTIVE_ERRORS)
            return self._skip(s)
        s.consecutive_errors = 0
        s.drawings = list(s.agent.draw.shapes)
        if self.time_budget_ms and elapsed_ms > self.time_budget_ms:
            return self._skip(s)
        s.last_velocity_cmd = action.velocity
        return action

    def _observe(self, s: _Slot) -> BattleObservation:
        b = s.body
        return BattleObservation(
            tick=self.tick, round=self.round, bot_id=b.bot_id,
            x=b.x, y=b.y, heading=b.heading, gun_heading=b.gun_heading,
            radar_heading=b.radar_heading, velocity=b.velocity, energy=b.energy,
            gun_heat=b.gun_heat, elevation=float(self.world.elevation_map[b.cell]),
            arena_width=self.world.width, arena_height=self.world.height,
            others=len(self.standing()) - 1,
            terrain=TerrainView(self.world, self._movement, s.agent.profile, b.x, b.y),
            inbox=self._comms.get_inbox(b.bot_id) if self.cfg.comms_enabled else [],
            team_messages=list(s.team_inbox),
            skipped_turns=s.skipped_turns,
            **{k: list(v) for k, v in s.events.items()},
        )

    # ------------------------------------------------------------------
    # Bullets
    # ------------------------------------------------------------------

    def _fire(self, s: _Slot, a: BattleAction) -> None:
        b = s.body
        if b.state != ALIVE or a.fire <= 0 or b.gun_heat > 0:
            return
        # Power is capped by remaining energy, so a bot can shoot itself down to
        # exactly 0 and become disabled (Robocode behaviour).
        power = min(clamp(a.fire, self.cfg.min_bullet_power, self.cfg.max_bullet_power), b.energy)
        if power < self.cfg.min_bullet_power:
            return
        b.energy -= power
        b.gun_heat = self.cfg.gun_heat(power)
        if b.energy <= 0:
            b.energy, b.state = 0.0, DISABLED
        z = float(self.world.elevation_map[b.cell]) + s.agent.profile.eye_height_offset
        bullet = Bullet(self._next_bullet_id, b.bot_id, b.x, b.y, z,
                        b.gun_heading, power, self.cfg.bullet_speed(power))
        self._bullets.append(bullet)
        self._next_bullet_id += 1
        self.scorer.shot(b.bot_id)
        s.events["bullet_fired"].append(BulletFired(
            bullet.bullet_id, bullet.x, bullet.y, bullet.heading, power, bullet.speed))

    def _move_bullets(self) -> None:
        """Robocode's bullet update (BulletPeer.update), one bullet after another in
        random order: move; the arena edge first; then the first robot its path
        touches (robots in random order); then other bullets, each by its latest
        path: this tick's if it has moved already, last tick's if not (a bullet fired
        this tick that hasn't moved yet can't be hit). Terrain, which Robocode
        doesn't have, stops a bullet where its path meets the ground."""
        half = self.cfg.body_half_width
        gone: set[int] = set()
        order = list(self._bullets)
        self._rng.shuffle(order)
        for bullet in order:
            if bullet.bullet_id in gone:
                continue
            x0, y0 = bullet.x, bullet.y
            nx, ny = bullet_next(bullet)
            bullet.line = (x0, y0, nx, ny)
            bullet.x, bullet.y = nx, ny
            block = terrain_block_t(x0, y0, nx, ny, bullet.z, self.world)
            if block is not None and block[1] == "arena":
                self._bullet_missed(bullet, x0, y0, nx, ny, block[0], "arena")
                gone.add(bullet.bullet_id)
                continue
            robots = [s for s in self.standing() if s.body.bot_id != bullet.shooter_id]
            self._rng.shuffle(robots)
            hit = None
            for s in robots:
                t = segment_box_t(x0, y0, nx, ny, s.body.x, s.body.y, half)
                if t is not None:
                    hit = (s, t)
                    break
            if hit is not None and (block is None or hit[1] <= block[0]):
                s, t = hit
                self._bullet_hits(bullet, s, x0 + (nx - x0) * t, y0 + (ny - y0) * t, nx, ny)
                gone.add(bullet.bullet_id)
                continue
            if block is not None:
                self._bullet_missed(bullet, x0, y0, nx, ny, block[0], block[1])
                gone.add(bullet.bullet_id)
                continue
            if self.cfg.bullet_collisions:
                for other in self._bullets:
                    if (other is bullet or other.bullet_id in gone or other.shooter_id == bullet.shooter_id
                            or other.line is None):
                        continue
                    t = segments_intersect_t(bullet.line[:2], bullet.line[2:], other.line[:2], other.line[2:])
                    if t is None:
                        continue
                    gone |= {bullet.bullet_id, other.bullet_id}
                    for mine, theirs in ((bullet, other), (other, bullet)):
                        shooter = self.slots.get(mine.shooter_id)
                        if shooter is not None:
                            shooter.events["bullet_hit_bullet"].append(BulletHitBullet(
                                mine.bullet_id, theirs.bullet_id, theirs.shooter_id, mine.x, mine.y,
                                theirs.heading, theirs.power, theirs.x, theirs.y))
                    self._frame_events.append({
                        "type": "bullet_hit_bullet", "bullets": [bullet.bullet_id, other.bullet_id],
                        "x": round(x0 + (nx - x0) * t, 3), "y": round(y0 + (ny - y0) * t, 3),
                        "z": round(bullet.z, 3)})
                    break
        self._bullets = [b for b in self._bullets if b.bullet_id not in gone]

    def _bullet_missed(self, bullet: Bullet, x0: float, y0: float, nx: float, ny: float,
                       t: float, reason: str) -> None:
        x, y = x0 + (nx - x0) * t, y0 + (ny - y0) * t
        shooter = self.slots.get(bullet.shooter_id)
        if shooter is not None:
            shooter.events["bullet_missed"].append(BulletMissed(bullet.bullet_id, bullet.power, reason, x, y))
        self._frame_events.append({"type": "bullet_missed", "bullet": bullet.bullet_id, "reason": reason,
                                   "x": round(x, 3), "y": round(y, 3), "z": round(bullet.z, 3)})

    def _bullet_hits(self, bullet: Bullet, target: _Slot, x: float, y: float, ex: float, ey: float) -> None:
        """(x, y): where it struck, for the viewer; (ex, ey): end of its move this tick, for bots."""
        dmg = self.cfg.damage(bullet.power)
        dealt = min(dmg, target.body.energy)
        shooter = self.slots[bullet.shooter_id]
        target.events["hit_by_bullet"].append(HitByBullet(
            bullet.bullet_id, bullet.shooter_id, normalize_heading(bullet.heading + 180),
            bullet.power, dmg, ex, ey))
        self.scorer.bullet_hit(bullet.shooter_id, target.body.bot_id, dealt)
        self._damage(target, dmg, attacker=bullet.shooter_id)
        friendly = self.scorer.friends(bullet.shooter_id, target.body.bot_id)
        if shooter.body.state != DEAD and not friendly:
            shooter.body.energy += self.cfg.energy_return(bullet.power, dealt)
            if shooter.body.state == DISABLED and shooter.body.energy > 0:
                shooter.body.state = ALIVE
        shooter.events["bullet_hit"].append(BulletHit(
            bullet.bullet_id, target.body.bot_id, bullet.power, dmg, max(0.0, target.body.energy), ex, ey))
        self._frame_events.append({
            "type": "bullet_hit", "bullet": bullet.bullet_id, "shooter": bullet.shooter_id,
            "target": target.body.bot_id, "damage": round(dmg, 2),
            "x": round(x, 3), "y": round(y, 3), "z": round(bullet.z, 3)})

    # ------------------------------------------------------------------
    # Bodies
    # ------------------------------------------------------------------

    def _move(self, s: _Slot, a: BattleAction) -> None:
        b = s.body
        if b.state != ALIVE:
            b.velocity = 0.0
            return
        b.velocity = next_velocity(b.velocity, a.velocity, self.cfg)
        if b.velocity == 0:
            return
        rad = math.radians(b.heading)
        nx, ny = b.x + math.sin(rad) * b.velocity, b.y + math.cos(rad) * b.velocity
        half = self.cfg.body_half_width

        reason = blocked_reason(b.x, b.y, nx, ny, self.world, self._movement, s.agent.profile, half)
        if reason is not None:
            dmg = self.cfg.wall_damage(b.velocity)
            # Bearing of the wall: the direction we were driving in.
            bearing = b.heading if b.velocity > 0 else normalize_heading(b.heading + 180)
            s.events["hit_wall"].append(HitWall(bearing, dmg))
            self._frame_events.append({"type": "hit_wall", "bot": b.bot_id})
            b.velocity = 0.0
            self._damage(s, dmg, attacker=None)
            return

        for other in self.standing():
            o = other.body
            if o.bot_id == b.bot_id or not boxes_overlap(nx, ny, o.x, o.y, half):
                continue
            # Robocode: a bot moving away from the one it touches isn't stopped.
            if distance(nx, ny, o.x, o.y) >= distance(b.x, b.y, o.x, o.y):
                continue
            dmg = self.cfg.ram_damage
            s.events["hit_bot"].append(HitBot(o.bot_id, heading_to(b.x, b.y, o.x, o.y), dmg, True))
            other.events["hit_bot"].append(HitBot(b.bot_id, heading_to(o.x, o.y, b.x, b.y), dmg, False))
            self._frame_events.append({"type": "hit_bot", "bot": b.bot_id, "other": o.bot_id})
            b.velocity = 0.0
            self.scorer.ram(b.bot_id, o.bot_id, min(dmg, o.energy))
            self._damage(other, dmg, attacker=b.bot_id, ram=True)
            self._damage(s, dmg, attacker=None)
            return

        b.x, b.y = nx, ny

    def _damage(self, s: _Slot, amount: float, attacker: int | None, ram: bool = False) -> None:
        if amount <= 0 or s.body.state == DEAD:
            return
        self._ticks_since_damage = 0
        s.body.energy -= amount
        if attacker is not None:
            s.killer, s.killed_by_ram = attacker, ram
        if s.body.energy <= 0:
            s.body.energy = 0.0
            s.body.state = DEAD  # resolved into scoring in _resolve_deaths()

    def _inactivity(self) -> None:
        """Robocode's stalemate breaker: after inactivity_time ticks without any
        damage, every bot loses inactivity_energy_drain per tick."""
        self._ticks_since_damage += 1
        # Robocode drains from the (inactivity_time + 2)nd quiet tick on (its turns count from 0).
        if not self.cfg.inactivity_time or self._ticks_since_damage <= self.cfg.inactivity_time + 1:
            return
        for s in self.standing():
            # Robocode: at 0 a bot is disabled first and dies at the next drain.
            if s.body.state == DISABLED and s.body.energy <= 0:
                s.body.state = DEAD
                continue
            s.body.energy -= self.cfg.inactivity_energy_drain
            if s.body.energy <= 1e-9:      # 0.1 steps don't add up to exactly 0 in floating point
                s.body.energy, s.body.state = 0.0, DISABLED
        self._ticks_since_damage = self.cfg.inactivity_time + 2  # drain doesn't reset it

    # ------------------------------------------------------------------
    # Radar and comms
    # ------------------------------------------------------------------

    def _radar_sweep(self, s: _Slot) -> None:
        b = s.body
        for other in self.standing():
            o = other.body
            if o.bot_id == b.bot_id:
                continue
            if not in_radar_arc(b, o.x, o.y, self.cfg.body_half_width, self.cfg.radar_range):
                continue
            if self.cfg.radar_requires_los and not self._visibility.has_line_of_sight(
                    b.cell, o.cell, s.scan_profile):
                continue
            s.events["scanned_bots"].append(ScannedBot(
                bot_id=o.bot_id, name=other.agent.name, class_name=_class_name(other.agent),
                bearing=heading_to(b.x, b.y, o.x, o.y), distance=distance(b.x, b.y, o.x, o.y),
                heading=o.heading, velocity=o.velocity, energy=o.energy,
                elevation=float(self.world.elevation_map[o.cell]),
                teammate=self.scorer.friends(b.bot_id, o.bot_id)))
            self._frame_events.append({"type": "scan", "bot": b.bot_id, "target": o.bot_id})

    def _shout(self, s: _Slot, a: BattleAction) -> None:
        if not self.cfg.comms_enabled or a.shout is None:
            return
        target = self.slots.get(a.shout.recipient_id)
        if target is None or target.body.state == DEAD:
            return
        self._comms.send(s.body.bot_id, s.body.cell, s.agent.profile,
                         target.body.bot_id, target.body.cell, MessageType.SIGNAL,
                         {"kind": a.shout.kind, **a.shout.payload})

    def _deliver_team_messages(self) -> None:
        rng = self.cfg.team_message_range
        for sender_id, to, data in self._outgoing:
            sender = self.slots[sender_id]
            if sender.agent.team is None:
                continue
            for r in self.standing():
                rid = r.body.bot_id
                if not self.scorer.friends(sender_id, rid) or (to is not None and rid != to):
                    continue
                if rng is not None:
                    profile = dataclasses.replace(sender.agent.profile, max_perception_range=rng)
                    if not self._visibility.has_line_of_sight(sender.body.cell, r.body.cell, profile):
                        continue
                r.team_inbox.append(TeamMessage(sender_id, sender.agent.name, data))
        self._outgoing = []

    def _resolve_deaths(self) -> None:
        newly_dead = [s for s in self.slots.values()
                      if s.body.state == DEAD and s.body.bot_id not in self.scorer.death_order]
        for s in newly_dead:
            survivors = [o.body.bot_id for o in self.standing()]
            self.scorer.death(s.body.bot_id, s.killer, s.killed_by_ram, survivors)
            for o in self.standing():
                o.events["bot_death"].append(BotDeath(s.body.bot_id, s.agent.name))
            self._frame_events.append({"type": "death", "bot": s.body.bot_id})
            s.agent.on_death()

    # ------------------------------------------------------------------
    # Round end and viewer frames
    # ------------------------------------------------------------------

    def finish(self) -> list[int]:
        """Score placements, notify bots. Returns bot ids ranked 1st first."""
        survivors = sorted(((s.body.bot_id, s.body.energy) for s in self.standing()),
                           key=lambda p: -p[1])
        ranking = self.scorer.finish(survivors, len(self.slots))
        teams = self.teams_standing()
        winner = next(iter(teams)) if len(teams) == 1 else None
        for s in self.slots.values():
            s.agent.on_round_end(won=self.scorer.team_of(s.body.bot_id) == winner)
        return ranking

    def frame(self) -> dict[str, Any]:
        return {
            "type": "tick",
            "round": self.round,
            "tick": self.tick,
            "bots": [
                {"id": s.body.bot_id, "name": s.agent.name,
                 "x": round(s.body.x, 3), "y": round(s.body.y, 3),
                 "z": round(float(self.world.elevation_map[s.body.cell]), 3),
                 "heading": round(s.body.heading, 2), "gun": round(s.body.gun_heading, 2),
                 "radar": round(s.body.radar_heading, 2), "radar_prev": round(s.body.radar_prev, 2),
                 "energy": round(s.body.energy, 2), "gun_heat": round(s.body.gun_heat, 2),
                 "state": s.body.state}
                for s in self.slots.values()
            ],
            "bullets": [
                {"id": b.bullet_id, "x": round(b.x, 3), "y": round(b.y, 3), "z": round(b.z, 3),
                 "power": round(b.power, 2), "shooter": b.shooter_id}
                for b in self._bullets
            ],
            "events": self._frame_events,
            "drawings": {s.body.bot_id: s.drawings for s in self.slots.values() if s.drawings},
            "console": {s.body.bot_id: s.console for s in self.slots.values() if s.console},
            "inactive": self._ticks_since_damage > self.cfg.inactivity_time + 1 > 1,
            "scores": {bid: round(sc.total, 1) for bid, sc in self.scorer.scores.items()},
        }


def _class_name(agent: BattleAgent) -> str:
    """Real class name, also for subprocess proxies (which carry it as an attribute)."""
    return getattr(agent, "class_name", type(agent).__name__)
