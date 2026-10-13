# The sandbox: running bots you don't trust

A bot is Python code. Running someone else's bot normally means letting their
code do anything you can do on your machine. The sandbox runs each such bot in
its own locked-down Docker container instead, so a malicious bot can't reach
your files, the network or the other bots.

Terrabots uses it automatically for every bot that isn't yours:

| Where | Sandboxed |
|---|---|
| Tournament (`tools/tournament.py`) | everything in `contrib/` and `submissions/` |
| Setup screen (`terrabots-battle`) | community bots (`contrib/`): listed by reading the source, played sandboxed |
| Command line | `terrabots-battle --headless --sandbox ...`: every bot except the built-in ones |
| Python | `BattleRunner(config, [(SandboxEntry("pkg.mod:Class"), 1), ...])`; survival: `SandboxAgent.factory(entry)` |

The built-in demo bots, your own bots in `bots/` and bots you pass with
`--extra` run in-process as before, since they're yours.

## Setup

Docker, plus the sandbox image (Python and numpy only; build it once):

```bash
docker build -t terrabots-sandbox -f docker/sandbox.Dockerfile docker/
```

The engine's `terrabots` package and the bot's folder are mounted read-only at
run time, so the image doesn't need rebuilding when either changes. The bot's
files must be readable by other users (the container runs as an unprivileged
user), which is the default for files in a git checkout.

## What a sandboxed bot can't do

Each bot gets its own container (`terrabots.battle.sandbox.docker_command`):

- **No network** (`--network none`).
- **No access to your files.** It sees two folders, both read-only: the public
  engine package and its own folder. For `submissions/<author>/` and
  `contrib/<author>/` that's the author's folder only, so bots can't read each
  other's code. Symlinked submission folders are refused.
- **No writing** outside a 16 MB `/tmp` and its storage (`/data`, the 200 KB
  quota), both in memory and gone with the container.
- **Limited resources:** 512 MB of memory, one CPU, 64 processes. No Docker log
  files, so printing gigabytes doesn't fill your disk.
- **No privileges:** an unprivileged user, all Linux capabilities dropped, no
  privilege escalation.

And the engine trusts nothing it gets back:

- **Never imported on the host.** Bot classes are found by reading the source
  (`find_bots`), so not even the module's top level runs outside the container.
- **JSON, not pickle.** The process isolation (`bot_isolation = "process"`)
  exchanges pickles, which is fine for your own bots but would let a hostile
  bot run code in the engine. The sandbox speaks JSON and checks every reply
  (`terrabots.battle.wire`): finite numbers, sizes, known fields.
- **No self-made rules.** A bot's own movement profile (climb limit, eye height)
  is ignored; sandboxed bots use the standard one.
- **Stopped when misbehaving.** A late turn is skipped; no answer within the hard
  limit (2 s), a reply over 1 MB, a reply that isn't valid, or a crash stops the
  bot for the battle. The battle goes on without it.

`tests/test_sandbox.py` checks this with hostile bots: one probing the network,
other folders and read-only paths; one that never answers; one that eats all
memory; one sending invalid and oversized replies.

## What it doesn't protect against

Be clear about the limits:

- **Container escapes.** Docker containers share the host's kernel. A bot that
  exploits a kernel or Docker bug could get out. These bugs are rare and get
  patched; keep Docker and your system up to date. For high-stakes use, run the
  tournament in a throwaway VM.
- **CPU and time.** Within its limits a bot can keep one CPU busy during its
  battles; it can't slow down other bots' turns beyond that.
- **The public engine.** A bot can read the engine's source (it's public anyway)
  and everything in its own observation. It can't see other bots' state.
- **Your own bots aren't sandboxed.** Bots in `bots/` and `--extra` bots run
  in-process, as before.

## Speed

Measured on WSL2 with Docker 29: a container starts in about 0.5 s and a turn's
round trip is about 0.8 ms; all bots of a battle think in parallel. So a
1500-tick round costs roughly 1.2 s extra (an estimate from those two numbers). A
quick tournament with one sandboxed battle bot and one survival agent took 81 s
with 8 workers. Results are reproducible and identical to process isolation
(checked with the same bot both ways: bots are seeded per bot, same seed, same
results).

## Private submissions (for the maintainer)

Private submissions live in `submissions/<author>/` in your checkout. That
folder is git-ignored and never committed. To run the tournament:

```bash
git clone git@github.com:<author>/<their-bot-repo>.git /tmp/sub && cp -r /tmp/sub/<author> submissions/
python tools/tournament.py --extra mubot:MuBot@devbyandre --extra-agent mubot:MuBotSurvival@devbyandre
git add docs/leaderboard.json docs/leaderboard.md && git commit -m "Update leaderboard"
```

Private bots appear on the leaderboard with their class name and author, marked
"closed source"; their file names and descriptions are not published.
