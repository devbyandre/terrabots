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
`__init__.py`. Its code is then public under the MIT license, listed in the
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

## Good first contributions

- A new demo bot in `terrabots/agents/` with a one-line docstring (it shows up
  in the setup screen) and a test that it runs a battle without errors.
- A lesson or exercise built on Terrabots (statistics on battle results,
  a targeting technique, an ML experiment).
- Viewer improvements, checked in a real browser.

## Reporting bugs

Include the command or battle TOML, the seed, what you expected and what
happened. Seeded battles are reproducible, which makes bugs much easier to fix.
