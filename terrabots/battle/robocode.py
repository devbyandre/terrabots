"""
Robocode-style API for porting AdvancedRobots to Terrabots.

Robocode bots queue commands ("turn the radar 360°, drive 100 ahead") and the
game executes them over the following ticks, reporting progress through
getDistanceRemaining() & co. and through events. Terrabots' native BattleAgent
is per-tick instead. AdvancedRobot bridges the two, so a Java bot ports almost
line by line:

    Java                                   Python
    -------------------------------------  ---------------------------------------
    public void run() { while (true) {     def tick(self):          # once per turn
        setTurnRadarRight(360); execute();     self.set_turn_radar_right(360)
    } }
    public void onScannedRobot(            def on_scanned_robot(self, e):
        ScannedRobotEvent e) {                 self.set_fire(2)
        setFire(2); }
    getHeading(), getGunHeat(), getOthers() self.heading, self.gun_heat, self.others
    setAdjustGunForRobotTurn(true)          self.set_adjust_gun_for_robot_turn(True)

Each turn: remaining amounts are updated from what actually happened last tick,
events are delivered to the on_* handlers, then tick() runs, and the queued
commands become this tick's BattleAction.

Differences to know about:
- Distances are cells, not pixels (1 cell = 16 px, see config.PX_PER_CELL).
- Event bearings follow Robocode: `bearing` is relative to your body heading
  (-180..180); `absolute_bearing` is the heading from you to the target.
- set_fire() returns a Bullet record right away (like setFireBullet); its
  bullet_id is filled in when the engine confirms the shot next tick.
- Like setAhead in Robocode, hitting a wall or another bot clears the distance
  remaining.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from terrabots.battle.actions import BattleAction
from terrabots.battle.agent import BattleAgent
from terrabots.battle.geometry import normalize_angle
from terrabots.battle.observation import BattleObservation


# ---------------------------------------------------------------------------
# Robocode-shaped events
# ---------------------------------------------------------------------------

@dataclass
class Bullet:
    """A shot you fired (Robocode's robocode.Bullet)."""
    x: float
    y: float
    heading: float
    power: float
    velocity: float
    owner: str
    tick: int
    bullet_id: int | None = None    # known from the tick after firing
    active: bool = True
    victim: str | None = None


@dataclass(frozen=True)
class ScannedRobotEvent:
    name: str
    bot_id: int
    bearing: float            # relative to your body heading
    absolute_bearing: float
    distance: float
    heading: float
    velocity: float
    energy: float
    elevation: float


@dataclass(frozen=True)
class HitByBulletEvent:
    name: str                 # shooter
    bearing: float            # relative: where the bullet came from
    power: float
    damage: float


@dataclass(frozen=True)
class BulletHitEvent:
    name: str                 # victim
    energy: float             # victim's energy after the hit
    bullet: Bullet | None


@dataclass(frozen=True)
class BulletMissedEvent:
    bullet: Bullet | None


@dataclass(frozen=True)
class BulletHitBulletEvent:
    bullet: Bullet | None
    hit_bullet_owner: str


@dataclass(frozen=True)
class HitWallEvent:
    bearing: float            # relative to your body heading


@dataclass(frozen=True)
class HitRobotEvent:
    name: str
    bearing: float            # relative
    energy: float | None      # Robocode reports it; None when we haven't scanned it
    my_fault: bool


@dataclass(frozen=True)
class RobotDeathEvent:
    name: str


# ---------------------------------------------------------------------------
# AdvancedRobot
# ---------------------------------------------------------------------------

@dataclass
class _Queue:
    distance: float = 0.0
    body_turn: float = 0.0
    gun_turn: float = 0.0
    radar_turn: float = 0.0
    fire: float = 0.0
    max_velocity: float = math.inf
    completed: set[str] = field(default_factory=set)


class AdvancedRobot(BattleAgent):
    """Base class with Robocode's AdvancedRobot API. Override tick() and on_* handlers."""

    def __init__(self) -> None:
        super().__init__()
        self._q = _Queue()
        self._obs: BattleObservation | None = None
        self._prev: BattleObservation | None = None
        self._bullets: list[Bullet] = []        # fired, not yet resolved
        self._names: dict[int, str] = {}        # bot id -> name, from scans and events
        self._energies: dict[int, float] = {}

    # ------------------------------------------------------------------
    # Override these
    # ------------------------------------------------------------------

    def tick(self) -> None:
        """One iteration of Robocode's run() loop (everything before execute())."""

    def on_scanned_robot(self, e: ScannedRobotEvent) -> None: ...
    def on_hit_by_bullet(self, e: HitByBulletEvent) -> None: ...
    def on_bullet_hit(self, e: BulletHitEvent) -> None: ...
    def on_bullet_missed(self, e: BulletMissedEvent) -> None: ...
    def on_bullet_hit_bullet(self, e: BulletHitBulletEvent) -> None: ...
    def on_hit_wall(self, e: HitWallEvent) -> None: ...
    def on_hit_robot(self, e: HitRobotEvent) -> None: ...
    def on_robot_death(self, e: RobotDeathEvent) -> None: ...
    def on_skipped_turn(self) -> None: ...
    def on_win(self) -> None: ...
    def on_round_ended(self) -> None: ...
    # Robocode's built-in custom conditions, fired when a queued command finishes
    def on_move_complete(self) -> None: ...
    def on_turn_complete(self) -> None: ...
    def on_gun_turn_complete(self) -> None: ...
    def on_radar_turn_complete(self) -> None: ...

    # ------------------------------------------------------------------
    # Getters (Robocode: getX(), getHeading(), ...)
    # ------------------------------------------------------------------

    @property
    def obs(self) -> BattleObservation:
        assert self._obs is not None, "only available inside tick() and event handlers"
        return self._obs

    x = property(lambda self: self.obs.x)
    y = property(lambda self: self.obs.y)
    heading = property(lambda self: self.obs.heading)
    gun_heading = property(lambda self: self.obs.gun_heading)
    radar_heading = property(lambda self: self.obs.radar_heading)
    velocity = property(lambda self: self.obs.velocity)
    energy = property(lambda self: self.obs.energy)
    gun_heat = property(lambda self: self.obs.gun_heat)
    others = property(lambda self: self.obs.others)
    time = property(lambda self: self.obs.tick)
    round_num = property(lambda self: self.obs.round - 1)    # Robocode counts from 0
    battle_field_width = property(lambda self: self.obs.arena_width)
    battle_field_height = property(lambda self: self.obs.arena_height)
    gun_cooling_rate = property(lambda self: self.rules.gun_cooling_rate)
    distance_remaining = property(lambda self: self._q.distance)
    turn_remaining = property(lambda self: self._q.body_turn)
    gun_turn_remaining = property(lambda self: self._q.gun_turn)
    radar_turn_remaining = property(lambda self: self._q.radar_turn)

    # ------------------------------------------------------------------
    # Commands (Robocode: setAhead(), setTurnRight(), ...). They replace, not add.
    # ------------------------------------------------------------------

    def set_ahead(self, distance: float) -> None:
        self._q.distance = distance

    def set_back(self, distance: float) -> None:
        self._q.distance = -distance

    def set_turn_right(self, degrees: float) -> None:
        self._q.body_turn = degrees

    def set_turn_left(self, degrees: float) -> None:
        self._q.body_turn = -degrees

    def set_turn_gun_right(self, degrees: float) -> None:
        self._q.gun_turn = degrees

    def set_turn_gun_left(self, degrees: float) -> None:
        self._q.gun_turn = -degrees

    def set_turn_radar_right(self, degrees: float) -> None:
        self._q.radar_turn = degrees

    def set_turn_radar_left(self, degrees: float) -> None:
        self._q.radar_turn = -degrees

    def set_max_velocity(self, velocity: float) -> None:
        self._q.max_velocity = abs(velocity)

    def set_adjust_gun_for_robot_turn(self, independent: bool) -> None:
        self.adjust_gun_for_body_turn = independent

    def set_adjust_radar_for_gun_turn(self, independent: bool) -> None:
        self.adjust_radar_for_gun_turn = independent

    def set_fire(self, power: float) -> Bullet | None:
        """Fire this tick if the gun is cool; returns the Bullet (Robocode setFireBullet)."""
        if self.gun_heat > 0 or power <= 0 or self.energy <= 0:
            return None
        power = min(max(power, self.rules.min_bullet_power), self.rules.max_bullet_power, self.energy)
        self._q.fire = power
        bullet = Bullet(self.x, self.y, self.gun_heading, power, self.rules.bullet_speed(power),
                        self.name, self.time)
        self._bullets.append(bullet)
        return bullet

    # ------------------------------------------------------------------
    # Engine side
    # ------------------------------------------------------------------

    def decide(self, obs: BattleObservation) -> BattleAction:
        self._prev, self._obs = self._obs, obs
        self._q.fire = 0.0
        self._update_remaining()
        self._dispatch(obs)
        self.tick()
        return self._action()

    def on_round_end(self, won: bool) -> None:
        if won:
            self.on_win()
        self.on_round_ended()

    def _update_remaining(self) -> None:
        q, obs, prev = self._q, self._obs, self._prev
        if prev is None:
            return
        body = normalize_angle(obs.heading - prev.heading)
        gun = normalize_angle(obs.gun_heading - prev.gun_heading)
        radar = normalize_angle(obs.radar_heading - prev.radar_heading)
        own_gun = gun - (0.0 if self.adjust_gun_for_body_turn else body)
        own_radar = radar - (0.0 if self.adjust_radar_for_gun_turn else gun)

        def consume(remaining: float, done: float, event: str) -> float:
            if remaining == 0:
                return 0.0
            left = remaining - done
            if abs(left) < 1e-6 or (left > 0) != (remaining > 0):
                q.completed.add(event)
                return 0.0
            return left

        q.body_turn = consume(q.body_turn, body, "turn")
        q.gun_turn = consume(q.gun_turn, own_gun, "gun")
        q.radar_turn = consume(q.radar_turn, own_radar, "radar")
        q.distance = consume(q.distance, obs.velocity, "move")
        if obs.hit_wall or any(h.my_fault for h in obs.hit_bot):
            q.distance = 0.0

    def _dispatch(self, obs: BattleObservation) -> None:
        for s in obs.scanned_bots:
            self._names[s.bot_id] = s.name
            self._energies[s.bot_id] = s.energy
        by_id = {b.bullet_id: b for b in self._bullets if b.bullet_id is not None}
        unconfirmed = [b for b in self._bullets if b.bullet_id is None]
        for fired in obs.bullet_fired:
            if unconfirmed:
                b = unconfirmed.pop(0)
                b.bullet_id = fired.bullet_id
                by_id[b.bullet_id] = b
        for b in unconfirmed:   # requested last tick but the engine didn't fire it
            if b.tick < obs.tick - 1:
                self._bullets.remove(b)

        def resolve(bullet_id: int, victim: str | None = None) -> Bullet | None:
            b = by_id.get(bullet_id)
            if b is not None:
                b.active, b.victim = False, victim
                self._bullets.remove(b)
            return b

        rel = lambda absolute: normalize_angle(absolute - obs.heading)  # noqa: E731
        if obs.skipped_turns > (self._prev.skipped_turns if self._prev else 0):
            self.on_skipped_turn()
        for e in obs.bullet_hit_bullet:
            self.on_bullet_hit_bullet(BulletHitBulletEvent(
                resolve(e.bullet_id), self._names.get(e.other_shooter_id, str(e.other_shooter_id))))
        for e in obs.bullet_hit:
            name = self._names.get(e.target_id, str(e.target_id))
            self._energies[e.target_id] = e.target_energy
            self.on_bullet_hit(BulletHitEvent(name, e.target_energy, resolve(e.bullet_id, name)))
        for e in obs.bullet_missed:
            self.on_bullet_missed(BulletMissedEvent(resolve(e.bullet_id)))
        for e in obs.hit_by_bullet:
            self.on_hit_by_bullet(HitByBulletEvent(
                self._names.get(e.shooter_id, str(e.shooter_id)), rel(e.bearing), e.power, e.damage))
        for e in obs.hit_bot:
            self.on_hit_robot(HitRobotEvent(self._names.get(e.bot_id, str(e.bot_id)), rel(e.bearing),
                                            self._energies.get(e.bot_id), e.my_fault))
        for e in obs.hit_wall:
            self.on_hit_wall(HitWallEvent(rel(e.bearing)))
        for e in obs.bot_death:
            self.on_robot_death(RobotDeathEvent(e.name))
        for s in obs.scanned_bots:
            self.on_scanned_robot(ScannedRobotEvent(
                s.name, s.bot_id, rel(s.bearing), s.bearing, s.distance, s.heading,
                s.velocity, s.energy, s.elevation))

        completed, self._q.completed = self._q.completed, set()
        handlers = {"move": self.on_move_complete, "turn": self.on_turn_complete,
                    "gun": self.on_gun_turn_complete, "radar": self.on_radar_turn_complete}
        for name in ("move", "turn", "gun", "radar"):
            if name in completed:
                handlers[name]()

    def _action(self) -> BattleAction:
        q = self._q
        rem = abs(q.distance)
        if rem < 1e-6:
            velocity = 0.0
        else:
            stoppable = _max_stoppable_speed(rem, self.rules.deceleration)
            velocity = math.copysign(min(self.rules.max_velocity, q.max_velocity, stoppable),
                                     q.distance)
        return BattleAction(velocity=velocity, body_turn=q.body_turn, gun_turn=q.gun_turn,
                            radar_turn=q.radar_turn, fire=q.fire)


def _max_stoppable_speed(remaining: float, decel: float) -> float:
    """Fastest speed for this tick that still lets us brake to a stop within
    `remaining`, braking by `decel` per tick afterwards (v + (v-d) + (v-2d) + ...)."""
    def travel(v: float) -> float:
        n = int(v // decel)
        return (n + 1) * v - decel * n * (n + 1) / 2
    lo, hi = 0.0, remaining
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if travel(mid) <= remaining else (lo, mid)
    return lo
