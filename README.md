# Terrabots

A Python framework for building, studying, and competing with autonomous agents in a
2.5D world with terrain, elevation-aware line of sight and agent communication.
Inspired by Robocode. Today it runs a **survival mode** (foraging, energy, social
behaviour); a Robocode-style **battle mode** with tanks, radar and bullets is
specified in [docs/arena-spec.md](docs/arena-spec.md) and not built yet.

Designed as a teaching and research platform: build an agent in one file, run it
against others, measure what strategies actually win, and learn Python, AI, statistics,
and machine learning along the way.

---

## Key concepts

| Robocode concept | Terrabots equivalent |
|---|---|
| Tank bot | Creature agent |
| Shooting / targeting | Foraging / resource prediction |
| Anti-gravity movement | Repulsion-based flocking movement |
| GuessFactor histogram | Resource-location histogram |
| Health points | Energy (depletes each tick; replenished by foraging) |
| Round win/loss | Survival time / population fitness |
| Team coordination | LOS-gated, range-limited inter-agent messaging |

---

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q                     # run the test suite

terrabots-run                    # simulation + viewer: open http://localhost:8765/
terrabots-run --headless         # no browser, prints tick stats
terrabots-run --agent bots.wanderer:WandererAgent=5 --agent bots.my_bot:MyBot=5
```

**VS Code:** open the folder, accept the recommended extensions, run the task
*Terrabots: Setup venv*, then press F5 and pick a launch configuration. Breakpoints in
your bot's `decide()` work.

---

## Project layout

```
terrabots/
  framework/
    agent.py          # Abstract Agent base class — implement this
    actions.py        # Action dataclass agents return each tick
    observation.py    # Observation dataclass agents receive each tick
    simulation.py     # Simulation engine — wires the tick loop
  agents/             # Built-in demo bots (planned)
  world_terrain.py    # WorldGrid, Cell, TerrainType, VisibilityMgr, MovementResolver
  comms.py            # CommsMgr — LOS + range gated messaging
  viewer/
    server.py         # Serves the viewer page + WebSocket stream on one port
    index.html        # Three.js browser visualizer
  run.py              # terrabots-run CLI and procedural terrain
bots/
  wanderer.py         # Smallest example bot — copy this to start your own
docs/
  arena-spec.md       # Battle mode specification (next feature)
tests/
  test_world_terrain.py
  test_comms.py
  test_simulation.py
```

---

## Building your own agent

Subclass `Agent` and implement `decide()`. `on_birth()` and `on_message()` are optional:

```python
from terrabots.framework.agent import Agent
from terrabots.framework.actions import Action, MoveDirection
from terrabots.framework.observation import Observation

class MyAgent(Agent):
    def on_birth(self) -> None:
        """Called once when the agent enters the world. Set up internal state here."""
        self.food_tips: list[tuple[int, int]] = []

    def on_message(self, sender_id: int, kind: str, payload: dict) -> None:
        """Called before decide() for each message delivered to you this tick."""
        if "pos" in payload:
            self.food_tips.append(tuple(payload["pos"]))

    def decide(self, obs: Observation) -> Action:
        """Called every tick. Return what you want to do this tick."""
        if obs.nearest_resource:
            return Action(move_toward=obs.nearest_resource)
        if self.food_tips:
            return Action(move_toward=self.food_tips.pop())
        return Action(move_direction=MoveDirection.RANDOM)
```

Save it as `bots/my_agent.py` and run it against the Wanderer:

```bash
terrabots-run --agent bots.my_agent:MyAgent=5 --agent bots.wanderer:WandererAgent=5
```

Or from Python:

```python
from terrabots.framework.simulation import Simulation
from terrabots.world_terrain import WorldGrid

world = WorldGrid(64, 64)
sim = Simulation(world)
sim.add_agent(MyAgent, count=10)
sim.run(ticks=1000)
```

> Bots are ordinary Python code running in the simulator's process. Only run bots
> you trust.

---

## Educational goals

- **Statistics**: agents collect hit/find histograms and adapt over time
- **Machine learning**: plug in a PyTorch policy instead of a rule-based `decide()`
- **Emergent behaviour**: run 100 agents with simple rules and watch what happens
- **Multi-agent coordination**: implement flocking, role assignment, and broadcast protocols
- **Reinforcement learning**: `Observation.to_dict()` gives a flat feature dict; a full Gymnasium/PettingZoo wrapper is planned

---

## License

MIT — see [LICENSE](LICENSE). Attribution appreciated but not required.
Created by André Munzinger. Contributions welcome.
