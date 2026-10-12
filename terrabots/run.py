"""
Terrabots simulation entry point.

Usage:
    python -m terrabots.run                    # defaults: 64x64, 10 Wanderers, 500 ticks
    python -m terrabots.run --headless         # no viewer, prints stats
    python -m terrabots.run --ticks 200 --agents 20 --size 32
    python -m terrabots.run --agent bots.wanderer:WandererAgent=5 --agent mypackage.bots:MyAgent=5   # any installed bot package
    terrabots-run --help                       # when installed via pip

With the viewer on, open http://localhost:8765/ in a browser (page and
WebSocket share one port).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="terrabots-run",
        description="Run the Terrabots multi-agent simulation.",
    )
    p.add_argument("--size",     type=int,   default=64,    help="World size (NxN, default 64)")
    p.add_argument("--agents",   type=int,   default=10,    help="Number of Wanderer agents when no --agent is given (default 10)")
    p.add_argument("--agent",    action="append", metavar="MODULE:CLASS[=N]",
                   help="Agent class to spawn, repeatable, e.g. --agent bots.my_bot:MyBot=5")
    p.add_argument("--ticks",    type=int,   default=500,   help="Number of ticks to run (default 500)")
    p.add_argument("--host",     type=str,   default="localhost", help="WebSocket host (default localhost)")
    p.add_argument("--port",     type=int,   default=8765,  help="WebSocket port (default 8765)")
    p.add_argument("--headless", action="store_true",       help="Run without viewer WebSocket server")
    p.add_argument("--speed",    type=float, default=0.05,  help="Seconds between ticks when viewer is on (default 0.05)")
    p.add_argument("--seed",     type=int,   default=None,  help="Random seed for reproducibility")
    p.add_argument("--verbose",  action="store_true",       help="Print tick stats to stdout")
    p.add_argument("--log",      type=str,   default="WARNING",
                   choices=["DEBUG","INFO","WARNING","ERROR"],
                   help="Log level (default WARNING)")
    return p.parse_args()


def _build_world(size: int, seed: int | None):
    """Create a WorldGrid with procedural terrain."""
    import random
    from terrabots.map_generator import procedural

    if seed is not None:
        random.seed(seed)
    return procedural(size, size, rng=random)


def _load_agent_spec(spec: str) -> tuple[type, int]:
    """Parse 'package.module:ClassName[=count]' into (agent_class, count)."""
    import importlib
    import os

    # Console scripts (terrabots-run) don't put the working directory on sys.path;
    # add it so user bots in ./bots/ are importable just like with `python -m`.
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())

    target, _, count = spec.partition("=")
    module_name, _, class_name = target.partition(":")
    if not class_name:
        raise SystemExit(f"--agent '{spec}': expected 'module:ClassName[=count]'")
    module = importlib.import_module(module_name)
    return getattr(module, class_name), int(count or 1)


def _build_sim(args: argparse.Namespace):
    from terrabots.framework.simulation import Simulation, SimConfig

    world = _build_world(args.size, args.seed)
    sim = Simulation(world, config=SimConfig())
    specs = args.agent or [f"bots.wanderer:WandererAgent={args.agents}"]
    total = 0
    for spec in specs:
        agent_class, count = _load_agent_spec(spec)
        sim.add_agent(agent_class, count=count)
        total += count
        print(f"  {count:3d} x {agent_class.__name__}")
    return sim, total


async def _run_with_viewer(args: argparse.Namespace) -> None:
    from terrabots.viewer.server import ViewerServer

    sim, total = _build_sim(args)
    async with ViewerServer(sim, host=args.host, port=args.port) as srv:
        print(f"Terrabots simulation starting — {total} agents, {args.ticks} ticks")
        await srv.run_simulation(ticks=args.ticks, tick_delay=args.speed, verbose=args.verbose)
    print("Simulation complete.")


def _run_headless(args: argparse.Namespace) -> None:
    sim, total = _build_sim(args)
    print(f"Terrabots headless run — {total} agents, {args.ticks} ticks")
    snapshots = sim.run(ticks=args.ticks, verbose=True)
    last = snapshots[-1]
    print(f"\nFinal tick: {last.tick} | alive: {last.n_alive} | resources: {len(last.resources)}")
    survivors: dict[str, int] = {}
    for a in last.agents:
        if a["alive"]:
            survivors[a["class"]] = survivors.get(a["class"], 0) + 1
    print(f"Survivors by class: {survivors or 'none'}")


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=getattr(logging, args.log))

    if args.headless:
        _run_headless(args)
    else:
        try:
            asyncio.run(_run_with_viewer(args))
        except KeyboardInterrupt:
            print("\nStopped by user.")


if __name__ == "__main__":
    main()
