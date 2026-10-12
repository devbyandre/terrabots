"""
Simulation engine — wires the tick loop.

Responsibilities:
- Spawns agents at random passable cells
- Builds per-agent Observations from WorldGrid + VisibilityMgr state
- Calls agent lifecycle methods in the correct order
- Applies Actions: resolves RANDOM direction, enforces can_pass, deducts energy
- Manages resource regeneration on the WorldGrid
- Runs CommsMgr (send → deliver → agents read inbox → clear)
- Tracks tick statistics and emits state snapshots for the viewer

Design notes:
- World state is applied all-at-once at the end of each tick (position updates,
  energy changes, resource deductions). Agents that decide in the same tick cannot
  observe each other's moves from that tick -- they see last tick's state. This is
  the standard synchronous multi-agent model.
- Resources are stored as a dict {(x,y): float} on the Simulation, not on WorldGrid
  cells directly. WorldGrid tracks terrain/elevation; resources are a game-layer
  concern layered on top.
- The viewer receives a snapshot dict after each tick via an optional callback
  (on_tick_end). The websocket server registers this callback; headless runs omit it.
- random.seed is intentionally not set here -- callers control reproducibility.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Type

from terrabots.comms import CommsMgr, MessageType
from terrabots.framework.actions import Action, MoveDirection, Shout
from terrabots.framework.agent import Agent
from terrabots.framework.observation import (
    AgentPercept,
    Observation,
    ResourcePercept,
    TerrainPercept,
)
from terrabots.world_terrain import (
    Cell,
    CreatureMoveProfile,
    MovementResolver,
    TerrainType,
    VisibilityMgr,
    WorldGrid,
)

# ---------------------------------------------------------------------------
# Resource configuration (tunable per-sim)
# ---------------------------------------------------------------------------

@dataclass
class ResourceConfig:
    initial_density: float = 0.05     # fraction of cells that start with resources
    max_per_cell: float = 50.0
    regen_rate: float = 0.5           # units added per tick to each resource cell
    forage_amount: float = 20.0       # energy gained per tick when standing on a resource
    forage_cost: float = 2.0          # energy cost of foraging action itself
    spawn_rate: float = 0.3           # expected new resource cells per tick; without it
                                      # eaten-out cells never return and worlds starve


@dataclass
class SimConfig:
    metabolism_per_tick: float = 1.0  # energy lost by every agent every tick
    initial_energy: float = 100.0
    resource: ResourceConfig = field(default_factory=ResourceConfig)


# ---------------------------------------------------------------------------
# Tick statistics snapshot (emitted to viewer / recorder)
# ---------------------------------------------------------------------------

@dataclass
class TickSnapshot:
    tick: int
    agents: list[dict[str, Any]]      # [{id, pos, energy, alive}, ...]
    resources: dict[str, float]       # {"x,y": amount}
    n_alive: int
    n_messages_sent: int


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

class Simulation:
    """Main simulation engine.

    Usage:
        world = WorldGrid(64, 64)
        sim = Simulation(world)
        sim.add_agent(MyAgent, count=10)
        sim.run(ticks=500)
    """

    def __init__(
        self,
        world: WorldGrid,
        config: SimConfig | None = None,
        on_tick_end: Callable[[TickSnapshot], None] | None = None,
    ) -> None:
        self.world = world
        self.config = config or SimConfig()
        self.on_tick_end = on_tick_end

        self._visibility = VisibilityMgr(world)
        self._movement = MovementResolver(world)
        self._comms = CommsMgr(self._visibility)

        self._agents: dict[int, Agent] = {}
        self._next_id: int = 0

        # {(x,y): current_amount}
        self._resources: dict[tuple[int, int], float] = {}

        self._tick: int = 0
        self._messages_sent_this_tick: int = 0

        self._seed_resources()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _seed_resources(self) -> None:
        rc = self.config.resource
        for x in range(self.world.width):
            for y in range(self.world.height):
                cell = self.world.get(x, y)
                if cell.terrain in (TerrainType.PLAIN, TerrainType.STAIRS):
                    if random.random() < rc.initial_density:
                        self._resources[(x, y)] = rc.max_per_cell * random.uniform(0.3, 1.0)

    def add_agent(self, agent_class: Type[Agent], count: int = 1, **kwargs: Any) -> list[Agent]:
        """Spawn `count` agents of `agent_class` at random passable cells."""
        spawned: list[Agent] = []
        for _ in range(count):
            agent = agent_class(**kwargs)
            pos = self._random_passable_cell(agent.profile)
            agent.agent_id = self._next_id
            agent.pos = pos
            agent.energy = self.config.initial_energy
            self._next_id += 1
            self._agents[agent.agent_id] = agent
            agent.on_birth()
            spawned.append(agent)
        return spawned

    def _random_passable_cell(self, profile: CreatureMoveProfile) -> tuple[int, int]:
        attempts = 0
        while True:
            x = random.randrange(self.world.width)
            y = random.randrange(self.world.height)
            if self._movement.can_pass(x, y, profile):
                # Ensure no other agent is already here
                occupied = {a.pos for a in self._agents.values() if a.alive}
                if (x, y) not in occupied:
                    return (x, y)
            attempts += 1
            if attempts > 10_000:
                raise RuntimeError("Could not find a passable spawn cell after 10,000 attempts")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self, ticks: int, verbose: bool = False) -> list[TickSnapshot]:
        """Run the simulation for `ticks` ticks. Returns all tick snapshots."""
        snapshots: list[TickSnapshot] = []
        for _ in range(ticks):
            snap = self.step()
            snapshots.append(snap)
            if verbose and self._tick % 50 == 0:
                print(f"tick {self._tick:4d} | alive={snap.n_alive} | "
                      f"resources={len(self._resources)} | msgs={snap.n_messages_sent}")
            if snap.n_alive == 0:
                if verbose:
                    print(f"All agents dead at tick {self._tick}. Stopping.")
                break
        return snapshots

    def step(self) -> TickSnapshot:
        """Advance the simulation by one tick. Returns a snapshot of end state."""
        self._tick += 1
        self._messages_sent_this_tick = 0

        alive_agents = [a for a in self._agents.values() if a.alive]

        # 1. Build observations and dispatch on_message hooks
        observations: dict[int, Observation] = {}
        for agent in alive_agents:
            inbox = self._comms.get_inbox(agent.agent_id)
            for msg in inbox:
                agent.on_message(msg.sender_id, msg.type.name, msg.payload)
            obs = self._build_observation(agent, inbox)
            observations[agent.agent_id] = obs

        # 2. Collect decisions (all agents decide before any action is applied)
        decisions: dict[int, Action] = {}
        for agent in alive_agents:
            decisions[agent.agent_id] = agent.decide(observations[agent.agent_id])

        # 3. Clear last tick's comms mailboxes before new sends
        self._comms.clear()

        # 4. Apply actions
        occupied: set[tuple[int, int]] = {a.pos for a in alive_agents}
        for agent in alive_agents:
            action = decisions[agent.agent_id]
            self._apply_action(agent, action, occupied)

        # 5. Metabolism + death check
        for agent in alive_agents:
            agent.energy -= self.config.metabolism_per_tick
            if agent.energy <= 0:
                agent.alive = False
                agent.energy = 0.0
                agent.on_death()

        # 6. Deliver messages that were sent during this tick
        self._comms.deliver()

        # 7. Regenerate resources
        self._regen_resources()

        # 8. Build and emit snapshot
        snap = self._build_snapshot()
        if self.on_tick_end:
            self.on_tick_end(snap)
        return snap

    # ------------------------------------------------------------------
    # Action application
    # ------------------------------------------------------------------

    def _apply_action(
        self, agent: Agent, action: Action, occupied: set[tuple[int, int]]
    ) -> None:
        # --- Movement ---
        new_pos = self._resolve_move(agent, action, occupied)
        if new_pos != agent.pos:
            cost = self._movement.move_cost(agent.pos, new_pos, agent.profile)
            agent.energy -= cost
            occupied.discard(agent.pos)
            agent.pos = new_pos
            occupied.add(new_pos)

        # --- Foraging ---
        pos = agent.pos
        if pos in self._resources and self._resources[pos] > 0:
            rc = self.config.resource
            gained = min(rc.forage_amount, self._resources[pos])
            self._resources[pos] -= gained
            agent.energy += gained - rc.forage_cost
            if self._resources[pos] <= 0:
                del self._resources[pos]

        # --- Comms ---
        if action.shout is not None:
            self._apply_shout(agent, action.shout)

    def _resolve_move(
        self, agent: Agent, action: Action, occupied: set[tuple[int, int]]
    ) -> tuple[int, int]:
        """Resolve the agent's movement intent to a valid (x, y) or stay."""
        if action.move_toward is not None:
            direction = self._step_toward(agent.pos, action.move_toward)
        elif action.move_direction is not None:
            direction = action.move_direction
        else:
            return agent.pos

        if direction == MoveDirection.STAY:
            return agent.pos

        if direction == MoveDirection.RANDOM:
            return self._random_adjacent(agent, occupied)

        dx, dy = direction.as_delta()
        nx, ny = agent.pos[0] + dx, agent.pos[1] + dy
        if (
            self.world.in_bounds(nx, ny)
            and self._movement.can_pass(nx, ny, agent.profile, from_pos=agent.pos)
            and (nx, ny) not in occupied
        ):
            return (nx, ny)
        return agent.pos  # blocked; stay

    def _step_toward(
        self, origin: tuple[int, int], target: tuple[int, int]
    ) -> MoveDirection:
        """Return the MoveDirection that is one step closer to target, or STAY."""
        dx = target[0] - origin[0]
        dy = target[1] - origin[1]
        if dx == 0 and dy == 0:
            return MoveDirection.STAY
        # Clamp to unit direction
        sx = (1 if dx > 0 else -1) if dx != 0 else 0
        sy = (1 if dy > 0 else -1) if dy != 0 else 0
        for direction in MoveDirection:
            if direction.value == (sx, sy):
                return direction
        return MoveDirection.STAY

    def _random_adjacent(
        self, agent: Agent, occupied: set[tuple[int, int]]
    ) -> tuple[int, int]:
        directions = [d for d in MoveDirection
                      if d not in (MoveDirection.STAY, MoveDirection.RANDOM)]
        random.shuffle(directions)
        for d in directions:
            dx, dy = d.as_delta()
            nx, ny = agent.pos[0] + dx, agent.pos[1] + dy
            if (
                self.world.in_bounds(nx, ny)
                and self._movement.can_pass(nx, ny, agent.profile, from_pos=agent.pos)
                and (nx, ny) not in occupied
            ):
                return (nx, ny)
        return agent.pos

    def _apply_shout(self, sender: Agent, shout: Shout) -> None:
        recipient = self._agents.get(shout.recipient_id)
        if recipient is None or not recipient.alive:
            return
        sent = self._comms.send(
            sender_id=sender.agent_id,
            sender_pos=sender.pos,
            sender_profile=sender.profile,
            recipient_id=shout.recipient_id,
            recipient_pos=recipient.pos,
            message_type=MessageType.SIGNAL,
            payload={"kind": shout.kind, **shout.payload},
        )
        if sent:
            self._messages_sent_this_tick += 1

    # ------------------------------------------------------------------
    # Observation construction
    # ------------------------------------------------------------------

    def _build_observation(self, agent: Agent, inbox: list) -> Observation:
        visible_agents: list[AgentPercept] = []
        visible_resources: list[ResourcePercept] = []
        visible_terrain: list[TerrainPercept] = []
        nearest_resource: tuple[int, int] | None = None
        nearest_dist = math.inf

        # Check all alive agents for visibility
        for other in self._agents.values():
            if not other.alive or other.agent_id == agent.agent_id:
                continue
            if self._visibility.has_line_of_sight(agent.pos, other.pos, agent.profile):
                cell = self.world.get(*other.pos)
                visible_agents.append(AgentPercept(
                    agent_id=other.agent_id,
                    pos=other.pos,
                    energy=other.energy,
                    elevation=cell.elevation,
                ))

        # Check visible resource cells (check all known resources within range)
        for rpos, amount in self._resources.items():
            dx = rpos[0] - agent.pos[0]
            dy = rpos[1] - agent.pos[1]
            dist_sq = dx * dx + dy * dy
            r = agent.profile.max_perception_range
            if dist_sq <= r * r:
                if self._visibility.has_line_of_sight(agent.pos, rpos, agent.profile):
                    cell = self.world.get(*rpos)
                    visible_resources.append(ResourcePercept(
                        pos=rpos, amount=amount, elevation=cell.elevation
                    ))
                    if dist_sq < nearest_dist:
                        nearest_dist = dist_sq
                        nearest_resource = rpos

        # Visible terrain cells (within perception range + LOS)
        ax, ay = agent.pos
        r = int(agent.profile.max_perception_range)
        for tx in range(max(0, ax - r), min(self.world.width, ax + r + 1)):
            for ty in range(max(0, ay - r), min(self.world.height, ay + r + 1)):
                dx, dy = tx - ax, ty - ay
                if dx * dx + dy * dy > r * r:
                    continue
                if self._visibility.has_line_of_sight(agent.pos, (tx, ty), agent.profile):
                    cell = self.world.get(tx, ty)
                    visible_terrain.append(TerrainPercept(
                        pos=(tx, ty),
                        terrain_name=cell.terrain.name,
                        elevation=cell.elevation,
                        water_depth=cell.water_depth,
                    ))

        own_cell = self.world.get(*agent.pos)
        return Observation(
            tick=self._tick,
            agent_id=agent.agent_id,
            pos=agent.pos,
            energy=agent.energy,
            elevation=own_cell.elevation,
            visible_agents=visible_agents,
            visible_resources=visible_resources,
            visible_terrain=visible_terrain,
            nearest_resource=nearest_resource,
            inbox=list(inbox),
        )

    # ------------------------------------------------------------------
    # Resource regeneration
    # ------------------------------------------------------------------

    def _regen_resources(self) -> None:
        rc = self.config.resource
        for pos in list(self._resources.keys()):
            self._resources[pos] = min(
                rc.max_per_cell, self._resources[pos] + rc.regen_rate
            )
        self._spawn_resources()

    def _spawn_resources(self) -> None:
        """Add new resource cells at random PLAIN/STAIRS cells.

        spawn_rate is an expected count, so 0.3 means "one new cell roughly every
        three ticks". Food never spawns under an agent, so standing still on an
        eaten-out cell cannot farm it.
        """
        rc = self.config.resource
        whole, frac = divmod(rc.spawn_rate, 1.0)
        n_new = int(whole) + (1 if random.random() < frac else 0)
        if n_new == 0:
            return
        occupied = {a.pos for a in self._agents.values() if a.alive}
        for _ in range(n_new):
            pos = (random.randrange(self.world.width), random.randrange(self.world.height))
            # One attempt per spawn: on rough maps fewer spawns land, which is fine.
            if pos in self._resources or pos in occupied:
                continue
            if self.world.get(*pos).terrain in (TerrainType.PLAIN, TerrainType.STAIRS):
                self._resources[pos] = rc.max_per_cell * random.uniform(0.3, 1.0)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def _build_snapshot(self) -> TickSnapshot:
        return TickSnapshot(
            tick=self._tick,
            agents=[
                {
                    "id": a.agent_id,
                    "class": a.__class__.__name__,
                    "pos": list(a.pos),
                    "energy": round(a.energy, 2),
                    "alive": a.alive,
                    "elevation": self.world.get(*a.pos).elevation,
                }
                for a in self._agents.values()
            ],
            resources={f"{x},{y}": round(amt, 2) for (x, y), amt in self._resources.items()},
            n_alive=sum(1 for a in self._agents.values() if a.alive),
            n_messages_sent=self._messages_sent_this_tick,
        )

    # ------------------------------------------------------------------
    # World state export (for viewer)
    # ------------------------------------------------------------------

    def world_state(self) -> dict[str, Any]:
        """Static world description sent once at viewer connect."""
        terrain_data = []
        for x in range(self.world.width):
            for y in range(self.world.height):
                cell = self.world.get(x, y)
                terrain_data.append({
                    "x": x, "y": y,
                    "terrain": cell.terrain.name,
                    "elevation": round(cell.elevation, 3),
                    "water_depth": round(cell.water_depth, 3),
                })
        return {
            "width": self.world.width,
            "height": self.world.height,
            "terrain": terrain_data,
        }
