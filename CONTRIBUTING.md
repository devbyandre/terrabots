# Contributing to Terrabots

Thanks for helping. Terrabots is a teaching and research platform, so code that a
learner can read counts as much as code that works.

There are three kinds of contributions, each with its own section below:

- **[Lessons](#lessons-notebooks):** Jupyter notebooks that teach one concept
  with a bot (targeting, statistics, learning, swarm behaviour).
- **[Framework](#framework):** the engine, viewer, maps, adapters and tools,
  e.g. new rules like more realistic ballistics.
- **[Bots](#submit-a-bot):** for the tournament, private or public.

## License of contributions

Terrabots is licensed under the [Mozilla Public License 2.0](LICENSE). By opening
a pull request you agree that your contribution is licensed under the MPL-2.0 as
well (no separate agreement to sign). You keep the copyright on your work. Only
contribute code you wrote or are allowed to contribute under these terms; don't
copy code under licenses that are incompatible with the MPL (for example from
RoboRumble bots, see [docs/robocode-bots.md](docs/robocode-bots.md#licences)).

Your own bots and projects that only *use* Terrabots aren't affected: license
them as you like. Private bot submissions stay private (see below).

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

Got a bot you're proud of? Put it in the ring. Submitted bots take part in the
tournament behind the [leaderboard](docs/leaderboard.md) (1v1, melee and
survival rankings).

Once enough submissions are in, we run the competition and publish the results.
**Your code stays private unless you say otherwise.** There are two ways in:

### Private (the default)

Only your bot's name, your GitHub name and its scores are published, marked
"closed source". The code and its description are not published, not shared and
not reused; it's deleted from the tournament machine when you ask.

1. Put your bot in a **private** GitHub repository, as `<your-github-name>/<bot>.py`
   plus an empty `__init__.py` (one or more `BattleAgent` or survival `Agent`
   classes per file).
2. Give [@devbyandre](https://github.com/devbyandre) read access.
3. Open a ["Bot submission" issue](https://github.com/devbyandre/terrabots/issues/new?template=bot-submission.yml)
   with the repository's name. Don't paste code into the issue: issues are public.

### Public (only if you want to)

Open a pull request adding `contrib/<your-github-name>/<bot>.py` and an empty
`__init__.py`. Its code is then public under the MPL-2.0, listed in the
setup screen ("Community bots"), and learners can read it. The first line of the
class docstring is shown on the leaderboard.

### Before you submit

Check that it plays, sandboxed, the way the tournament will run it (needs Docker,
see [docs/sandbox.md](docs/sandbox.md)):

```bash
docker build -t terrabots-sandbox -f docker/sandbox.Dockerfile docker/
terrabots-battle --headless --sandbox --rounds 10 --bot contrib.<you>.<bot>:<Class> --bot terrabots.agents.crazy:Crazy
```

### Rules

- **Plain Python**, standard library plus numpy, nothing else to install.
- **Inside the sandbox:** every submitted bot runs in a locked-down container with
  no network and no access to anything but its own folder. `self.storage` works
  (200 KB, kept for one battle); files and connections don't.
- **Fair play:** use only what the observation and `self.rules` give you. The
  standard movement profile applies to everyone (a bot's own `profile` is ignored).
- **Be quick:** stay within the 20 ms `decide()` budget; slow turns are skipped,
  and a bot that stops answering is stopped.
- **Your own work.** Readable, with a docstring saying what the bot does.

Bots that break the rules or try to escape the sandbox are removed.

## Lessons (notebooks)

Most people meet Terrabots through a lesson, so a good notebook is one of the
most valuable contributions. Look at the [existing ones](notebooks/) first.

- **One concept per notebook**, stated in the first cell: what you'll learn,
  what you need to know already, how long it takes (aim for 20–40 minutes).
- **Learn by experiment.** Build a bot or change one, run seeded battles, look
  at the numbers. Explain the idea, then let the data show it.
- **Reproducible.** Seed every battle and random generator, so readers get the
  numbers in the saved outputs. Keep a full run under a few minutes on a laptop.
- **Saved outputs.** Commit the notebook *with* outputs (Restart & Run All
  first): GitHub shows them, so people can read a lesson before installing.
- **Only Terrabots' dependencies** plus what `pip install -e ".[notebooks]"`
  brings. If a lesson really needs more (scikit-learn, PyTorch), say so in the
  first cell and propose adding it to the `notebooks` extra.
- **Exercises** at the end, with hints rather than full solutions.
- **Sources** for the theory (papers, books, the RoboWiki).
- Name it `NN_topic.ipynb` with the next free number and add a row to the
  table in [notebooks/README.md](notebooks/README.md).

Ideas: wave surfing, guess factor targeting, Bayesian estimation of enemy
movement, A/B testing bots with paired battles, reinforcement learning,
genetic algorithms tuning a bot, flocking in survival mode, team strategies.

Open an issue with the idea first if you like; it's a good way to get feedback
before writing a long notebook.

## Framework

Engine changes affect every bot, so they need a bit more care.

- **Open an issue first** for anything bigger than a fix: a new rule, a new
  game mode, an API change. Say what it's for and what it changes for existing
  bots.
- **Robocode rules stay the default.** Battles with default settings match real
  Robocode tick by tick (checked with `tools/robocode_conformance/`), and the
  Robocode adapter and the leaderboard rely on that. New or more realistic rules
  (e.g. ballistic arcs, wind, bullets hitting terrain, recoil) go in as options
  in `BattleConfig` (`terrabots/battle/config.py`) whose default keeps today's
  behaviour, with a row in the settings schema of the setup screen
  (`terrabots/viewer/battle.html`), in the settings table of
  [docs/arena-spec.md](docs/arena-spec.md#3-battle-settings-battleconfig), and
  a few words in the physics section of [docs/battle-guide.md](docs/battle-guide.md#3-physics).
- **Keep the invariants** (see Ground rules) and keep seeded battles
  reproducible.
- **Tests with every rule**, plus a note in [CHANGELOG.md](CHANGELOG.md).
- **Bot API changes** need the bot templates, guides and notebooks updated in
  the same pull request, and should keep existing bots working where possible.
- Viewer changes: check them in a real browser and say which one.

Smaller things are always welcome: a new demo bot in `terrabots/agents/` (with a
one-line docstring, which shows in the setup screen, and a test that it runs a
battle), new maps, docs fixes, clearer error messages.

## Reporting bugs

Include the command or battle TOML, the seed, what you expected and what
happened. Seeded battles are reproducible, which makes bugs much easier to fix.
