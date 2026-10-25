# Community bots (public)

Bots whose authors chose to publish their code, under the MPL-2.0 license like
the rest of Terrabots. Each
author has a folder named after their GitHub user name:

```
contrib/
  your-github-name/
    __init__.py        # empty
    my_tank.py         # one or more BattleAgent (battle) or Agent (survival) classes
```

These are other people's code, so Terrabots treats them that way: the setup
screen lists them by reading the source (it never imports them) and they always
play in the [sandbox](../docs/sandbox.md), in the viewer and in the tournament.

Most submissions are private and never land here; they take part in the
tournament as "closed source". How to submit: [CONTRIBUTING.md](../CONTRIBUTING.md#submit-a-bot).
