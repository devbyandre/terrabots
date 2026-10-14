"""
terrabots-battle: run a Robocode-style battle, in the browser or headless.

    terrabots-battle                                   # setup screen at http://localhost:8765/
    terrabots-battle battles/example.toml              # setup screen pre-filled from the file
    terrabots-battle battles/example.toml --autostart  # start right away
    terrabots-battle battles/example.toml --headless   # no browser; prints + saves results
    terrabots-battle --headless --rounds 20 --seed 1 \\
        --bot terrabots.agents.tracker:Tracker=2 --bot bots.my_bot:MyBot

--bot entries replace the file's bots. Results are saved to results/<timestamp>.json/.csv.

A Robocode bot? --jar path/to/bot.jar (headless) runs it unchanged, sandboxed,
through the Robocode adapter (docs/robocode-bots.md).

Someone else's bot? Run it with --headless --sandbox: every bot that isn't a
built-in one (terrabots.*) runs in a locked-down Docker container and is never
imported here (see terrabots.battle.sandbox; needs Docker and the
terrabots-sandbox image).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from terrabots.battle.config import BattleConfigError, BattleFile, BotEntry

DEFAULT_BOTS = [
    BotEntry("terrabots.agents.tracker:Tracker", 1),
    BotEntry("terrabots.agents.spin_bot:SpinBot", 1),
    BotEntry("terrabots.agents.crazy:Crazy", 1),
    BotEntry("terrabots.agents.sitting_duck:SittingDuck", 1),
]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="terrabots-battle", description=__doc__.split("\n\n")[0].strip(),
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="\n".join(__doc__.split("\n")[3:]))
    p.add_argument("battle_file", nargs="?", help="battle TOML (settings + [[bots]])")
    p.add_argument("--headless", action="store_true", help="run without the browser viewer")
    p.add_argument("--autostart", action="store_true", help="viewer: start the battle immediately")
    p.add_argument("--bot", action="append", metavar="MODULE:CLASS[=N]",
                   help="bot to fight, repeatable; replaces the file's bots")
    p.add_argument("--extra-bot", action="append", default=[], metavar="MODULE:CLASS",
                   help="viewer: list this bot in the setup screen (e.g. from an installed package)")
    p.add_argument("--extra-agent", action="append", default=[], metavar="MODULE:CLASS",
                   help="viewer: list this survival agent in the Survival tab")
    p.add_argument("--rounds", type=int, help="override number of rounds")
    p.add_argument("--seed", type=int, help="override seed")
    p.add_argument("--isolation", choices=["none", "process"],
                   help="run each bot in its own process (overrides the battle file)")
    p.add_argument("--jar", action="append", default=[], metavar="BOT.jar",
                   help="headless: a Robocode bot jar to fight, sandboxed (repeatable)")
    p.add_argument("--sandbox", action="store_true",
                   help="headless: run every non-built-in bot in a Docker sandbox (for bots you don't trust)")
    p.add_argument("--no-time-limit", action="store_true",
                   help="never skip slow turns (also automatic under a debugger)")
    p.add_argument("--results-dir", default="results", help="where to save results (default results/)")
    p.add_argument("--data-dir", default="bot_data",
                   help="bots' persistent storage, one folder per bot class (default bot_data/)")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--log", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args(argv)


def _parse_bot(spec: str) -> BotEntry:
    target, _, count = spec.partition("=")
    if ":" not in target:
        raise SystemExit(f"--bot {spec!r}: expected 'module:ClassName[=count]'")
    return BotEntry(target, int(count or 1))


def load_battle(args: argparse.Namespace) -> BattleFile:
    try:
        bf = BattleFile.load(args.battle_file) if args.battle_file else BattleFile.from_dict({})
        overrides = {k: v for k, v in (("rounds", args.rounds), ("seed", args.seed),
                                        ("bot_isolation", args.isolation)) if v is not None}
        if overrides:
            bf.config = type(bf.config).from_dict({**bf.config.to_dict(), **overrides})
    except (BattleConfigError, OSError) as exc:
        raise SystemExit(f"terrabots-battle: {exc}") from exc
    if args.bot:
        bf.bots = [_parse_bot(s) for s in args.bot]
    if not bf.bots and not bf.teams:
        bf.bots = list(DEFAULT_BOTS)
    return bf


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log))
    bf = load_battle(args)
    budget = None if args.no_time_limit else "config"

    if args.jar and not args.headless:
        raise SystemExit("terrabots-battle: --jar works with --headless only")
    if args.sandbox and not args.headless:
        raise SystemExit("terrabots-battle: --sandbox works with --headless only (the setup screen "
                         "imports the bots it lists)")
    if args.headless:
        from terrabots.battle.config import TeamEntry
        from terrabots.battle.runner import BattleRunner
        from terrabots.battle.sandbox import SandboxEntry

        def place(b: BotEntry):
            trusted = not args.sandbox or b.spec.startswith("terrabots.")
            return b if trusted else (SandboxEntry(b.spec), b.count)

        from terrabots.battle.sandbox import JarEntry, SandboxError

        try:
            jars = [(e, 1) for path in args.jar for e in JarEntry.from_jar(path)[:1]]
        except (SandboxError, OSError, ValueError) as exc:
            raise SystemExit(f"terrabots-battle: {exc}") from exc
        if args.jar and not args.bot and len(jars) + sum(b.count for b in bf.bots) < 2:
            raise SystemExit("terrabots-battle: add an opponent with --bot")
        try:
            runner = BattleRunner(bf.config, [place(b) for b in bf.bots] + jars, time_budget_ms=budget,
                                  data_dir=args.data_dir,
                                  teams=[TeamEntry(t.name, [place(m) for m in t.members]) for t in bf.teams])
        except (ImportError, AttributeError, ValueError, RuntimeError) as exc:
            raise SystemExit(f"terrabots-battle: {exc}") from exc
        n_bots = sum(b.count for b in bf.bots) + sum(m.count for t in bf.teams for m in t.members)
        print(f"Terrabots battle: {n_bots} bots, {bf.config.rounds} rounds, "
              f"{bf.config.width}x{bf.config.height} {bf.config.terrain}, seed {bf.config.seed}")
        results = runner.run(verbose=True)
        print()
        print(results.table())
        print(f"\nSaved {results.save(args.results_dir)}")
        return

    from terrabots.viewer.battle_server import BattleServer

    server = BattleServer(bf, extra_specs=args.extra_bot, extra_agents=args.extra_agent,
                          host=args.host, port=args.port,
                          results_dir=args.results_dir, data_dir=args.data_dir, time_budget_ms=budget,
                          autostart=args.autostart)
    try:
        asyncio.run(server.serve_forever())
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
