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
  elevation only. `CLAUDE.md` lists them all.
- **Templates stay tiny.** `bots/first_tank.py` and `bots/wanderer.py` are the
  first files a learner reads.

## Good first contributions

- A new demo bot in `terrabots/agents/` with a one-line docstring (it shows up
  in the setup screen) and a test that it runs a battle without errors.
- A lesson or exercise built on Terrabots (statistics on battle results,
  a targeting technique, an ML experiment).
- Viewer improvements, checked in a real browser.

## Reporting bugs

Include the command or battle TOML, the seed, what you expected and what
happened. Seeded battles are reproducible, which makes bugs much easier to fix.
