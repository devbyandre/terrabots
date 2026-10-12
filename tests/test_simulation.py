"""
Integration tests for the simulation tick loop.

Tests:
1. Basic tick advances: energy consumed, tick counter increments.
2. Foraging: standing on a resource cell gains energy.
3. Death: agent with low energy dies after enough ticks.
4. Multi-agent: multiple agents co-exist without collision.
5. Resource regeneration: resources grow back over time.
6. world_state() output is well-formed.
"""

import sys
import os
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from terrabots.world_terrain import WorldGrid, TerrainType
from terrabots.framework.simulation import Simulation, SimConfig, ResourceConfig
from terrabots.framework.agent import Agent
from terrabots.framework.actions import Action, MoveDirection
from terrabots.framework.observation import Observation


# ---------------------------------------------------------------------------
# Minimal test agent
# ---------------------------------------------------------------------------

class StayAgent(Agent):
    """Agent that never moves — used to isolate foraging / energy mechanics."""
    def decide(self, obs: Observation) -> Action:
        return Action()  # STAY


class MoveNorthAgent(Agent):
    """Agent that always tries to move north."""
    def decide(self, obs: Observation) -> Action:
        return Action(move_direction=MoveDirection.NORTH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def flat_world(w: int = 16, h: int = 16) -> WorldGrid:
    """Minimal flat PLAIN world with no resources seeded (we add manually)."""
    world = WorldGrid(w, h)
    for x in range(w):
        for y in range(h):
            cell = world.get(x, y)
            cell.terrain = TerrainType.PLAIN
            cell.elevation = 0.0
            world.elevation_map[x, y] = 0.0
    return world


def no_resource_config() -> ResourceConfig:
    return ResourceConfig(initial_density=0.0, spawn_rate=0.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_tick_counter():
    """sim.step() increments the internal tick counter."""
    world = flat_world()
    sim = Simulation(world, SimConfig(resource=no_resource_config()))
    sim.add_agent(StayAgent)
    snap = sim.step()
    assert snap.tick == 1
    snap = sim.step()
    assert snap.tick == 2


def test_metabolism_deducted():
    """Each tick reduces agent energy by metabolism_per_tick."""
    world = flat_world()
    cfg = SimConfig(initial_energy=100.0, metabolism_per_tick=2.0,
                    resource=no_resource_config())
    sim = Simulation(world, cfg)
    agents = sim.add_agent(StayAgent)
    sim.step()
    assert agents[0].energy == pytest_approx(98.0, abs=0.01)


def test_agent_dies_when_energy_exhausted():
    """Agent dies once energy drops to zero."""
    world = flat_world()
    cfg = SimConfig(initial_energy=3.0, metabolism_per_tick=1.0,
                    resource=no_resource_config())
    sim = Simulation(world, cfg)
    agents = sim.add_agent(StayAgent)
    # tick 1: energy 2.0 — alive
    snap = sim.step()
    assert agents[0].alive
    # tick 2: energy 1.0 — alive
    sim.step()
    assert agents[0].alive
    # tick 3: energy 0.0 → dies
    snap = sim.step()
    assert not agents[0].alive
    assert snap.n_alive == 0


def test_foraging_gains_energy():
    """Agent standing on a full resource cell gains energy (minus forage_cost)."""
    world = flat_world()
    rc = ResourceConfig(
        initial_density=0.0,
        forage_amount=20.0,
        forage_cost=2.0,
        regen_rate=0.0,
        max_per_cell=50.0,
    )
    cfg = SimConfig(initial_energy=100.0, metabolism_per_tick=1.0, resource=rc)
    sim = Simulation(world, cfg)
    agents = sim.add_agent(StayAgent)

    # Place a full resource at the agent's spawn position
    spawn = agents[0].pos
    sim._resources[spawn] = 50.0

    sim.step()
    # energy: 100 + (forage_amount - forage_cost) - metabolism = 100 + 18 - 1 = 117
    assert agents[0].energy > 100.0


def test_resource_depletes():
    """Foraging depletes the resource cell."""
    world = flat_world()
    rc = ResourceConfig(initial_density=0.0, forage_amount=50.0, forage_cost=0.0,
                        regen_rate=0.0, max_per_cell=50.0)
    cfg = SimConfig(initial_energy=100.0, metabolism_per_tick=0.0, resource=rc)
    sim = Simulation(world, cfg)
    agents = sim.add_agent(StayAgent)
    spawn = agents[0].pos
    sim._resources[spawn] = 50.0

    sim.step()
    assert spawn not in sim._resources  # fully consumed


def test_resource_regenerates():
    """Resources below max grow by regen_rate per tick."""
    world = flat_world()
    rc = ResourceConfig(initial_density=0.0, regen_rate=5.0, max_per_cell=50.0,
                        forage_amount=0.0, forage_cost=0.0)
    cfg = SimConfig(initial_energy=200.0, metabolism_per_tick=0.0, resource=rc)
    sim = Simulation(world, cfg)
    # Manually seed a partial resource at a cell with no agent on it
    sim._resources[(5, 5)] = 10.0

    sim.step()
    assert sim._resources[(5, 5)] == pytest_approx(15.0, abs=0.01)


def test_resources_respawn_after_depletion():
    """New resource cells appear over time even when the world starts empty."""
    random.seed(1)
    world = flat_world()
    rc = ResourceConfig(initial_density=0.0, spawn_rate=1.0)
    sim = Simulation(world, SimConfig(metabolism_per_tick=0.0, resource=rc))
    for _ in range(20):
        sim.step()
    assert len(sim._resources) > 0


def test_no_spawn_when_rate_zero():
    random.seed(1)
    world = flat_world()
    sim = Simulation(world, SimConfig(resource=no_resource_config()))
    for _ in range(50):
        sim.step()
    assert sim._resources == {}


def test_resources_never_spawn_under_agents():
    random.seed(2)
    world = flat_world(4, 4)
    rc = ResourceConfig(initial_density=0.0, spawn_rate=5.0, forage_amount=0.0)
    sim = Simulation(world, SimConfig(metabolism_per_tick=0.0, resource=rc))
    agents = sim.add_agent(StayAgent, count=4)
    for _ in range(30):
        sim.step()
    assert not ({a.pos for a in agents} & set(sim._resources))


def test_multi_agent_no_collision():
    """Multiple agents spawn without occupying the same cell."""
    random.seed(0)
    world = flat_world(32, 32)
    cfg = SimConfig(resource=no_resource_config())
    sim = Simulation(world, cfg)
    agents = sim.add_agent(StayAgent, count=20)
    positions = [a.pos for a in agents]
    assert len(set(positions)) == len(positions), "Duplicate spawn positions!"


def test_world_state_shape():
    """world_state() returns width, height, and one entry per cell."""
    world = flat_world(8, 10)
    sim = Simulation(world, SimConfig(resource=no_resource_config()))
    ws = sim.world_state()
    assert ws["width"] == 8
    assert ws["height"] == 10
    assert len(ws["terrain"]) == 80
    cell = ws["terrain"][0]
    assert {"x", "y", "terrain", "elevation", "water_depth"} <= set(cell)


def test_snapshot_agents_list():
    """TickSnapshot.agents contains one entry per agent."""
    world = flat_world()
    sim = Simulation(world, SimConfig(resource=no_resource_config()))
    sim.add_agent(StayAgent, count=3)
    snap = sim.step()
    assert len(snap.agents) == 3
    for a in snap.agents:
        assert {"id", "pos", "energy", "alive", "class"} <= set(a)


# ---------------------------------------------------------------------------
# Simple float approx helper (avoids importing pytest directly)
# ---------------------------------------------------------------------------

class pytest_approx:
    def __init__(self, expected, abs=1e-6):
        self._expected = expected
        self._abs = abs

    def __eq__(self, actual):
        return abs(actual - self._expected) <= self._abs

    def __repr__(self):
        return f"≈{self._expected}±{self._abs}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all():
    tests = [
        test_tick_counter,
        test_metabolism_deducted,
        test_agent_dies_when_energy_exhausted,
        test_foraging_gains_energy,
        test_resource_depletes,
        test_resource_regenerates,
        test_resources_respawn_after_depletion,
        test_no_spawn_when_rate_zero,
        test_resources_never_spawn_under_agents,
        test_multi_agent_no_collision,
        test_world_state_shape,
        test_snapshot_agents_list,
    ]
    passed = failed = 0
    for fn in tests:
        random.seed(42)
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} passed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _run_all()
