# Notebooks

Hands-on lessons that run battles and survival worlds right in Jupyter: no
viewer, results in seconds, plots inline. GitHub shows them with their outputs,
so you can read them before running anything.

| Notebook | You learn | Time |
|---|---|---|
| [1 · Your first tank](01_first_tank.ipynb) | the bot API, head-on vs. linear targeting, measuring hit rates | 20 min |
| [2 · Analysing battles](02_analysing_battles.ipynb) | seeded experiments, confidence intervals, paired comparisons | 30 min |
| [3 · Survival: when to leave a patch](03_survival_foraging.ipynb) | Charnov's marginal value theorem, tested in simulation | 30 min |

```bash
pip install -e ".[notebooks]"
jupyter lab notebooks/
```

In VS Code, open a notebook and pick the `.venv` interpreter as kernel.
Every experiment is seeded, so you get the same numbers as the saved outputs.
The guides go deeper: [battle guide](../docs/battle-guide.md),
[survival guide](../docs/survival-guide.md).
