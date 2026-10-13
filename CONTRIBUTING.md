# Contributing to Terrabots

Thanks for helping. Terrabots is a teaching and research platform, so code that a
learner can read counts as much as code that works.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Ground rules

- **Small, focused changes.** One concern per pull request; explain *why* in the
  description and the commit message (imperative mood: "Add radar trail", not
  "Added").
- **Tests with features.** New rules or behaviour come with tests in `tests/`.
  Seed anything random that a test asserts on.
- **Readable first.** Type hints, dataclasses for plain data, comments that
  explain why rather than what. Simple beats clever.
- **Keep the invariants.** Agents decide on the same pre-tick state; agents only
  see what they perceive (no global state in observations); line of sight is
  elevation only. The module docstrings describe them.
- **Templates stay tiny.** `bots/first_tank.py` and `bots/wanderer.py` are the
  first files a learner reads.

## Submit a bot

Got a bot you're proud of? Put it in the ring. Every bot in `contrib/` takes part
in the tournament behind the [leaderboard](docs/leaderboard.md) (1v1, melee and
survival rankings, re-run every week and whenever a bot is added).

1. Fork the repo and add your bot as `contrib/<your-github-name>/<bot>.py`, with an
   empty `__init__.py` next to it. One or more `BattleAgent` (battle) or `Agent`
   (survival) classes per file; the first line of the class docstring is shown in
   the setup screen and on the leaderboard.
2. Check it plays: `terrabots-battle --headless --rounds 10 --bot contrib.<you>.<bot>:<Class> --bot terrabots.agents.crazy:Crazy`
   and, if you like, `python tools/tournament.py --quick`.
3. Open a pull request (or a "Bot submission" issue with a link to your code).

Rules, so the competition stays fair and safe for everyone who runs it:

- **Plain Python, MIT licensed**, standard library plus numpy. Other
  dependencies only if the maintainers agree.
- **No files or network:** use `self.storage` for data that should survive
  between battles (200 KB); don't read or write anything else, don't open
  connections, don't start processes or threads.
- **Fair play:** use only what the observation and `self.rules` give you; no
  reading other bots' memory, the engine's internals or the RNG state.
- **Be quick:** stay within the 20 ms decide() budget; slow turns are skipped.
- One file per bot, readable, with a docstring saying what it does. Learners read
  these.

Maintainers review submissions before merging (bots are code), and may remove
bots that break the rules.

## Good first contributions

- A new demo bot in `terrabots/agents/` with a one-line docstring (it shows up
  in the setup screen) and a test that it runs a battle without errors.
- A lesson or exercise built on Terrabots (statistics on battle results,
  a targeting technique, an ML experiment).
- Viewer improvements, checked in a real browser.

## Reporting bugs

Include the command or battle TOML, the seed, what you expected and what
happened. Seeded battles are reproducible, which makes bugs much easier to fix.
