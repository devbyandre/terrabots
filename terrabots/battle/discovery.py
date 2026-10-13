"""
Find battle bots for the setup screen.

Scans ./bots/*.py (your bots) and terrabots/agents/*.py (built-in demo bots) for
BattleAgent subclasses (battle) or Agent subclasses (survival) defined in those files. Extra specs (e.g. a bot from an
installed package, `mypackage.bots:MyTank`) can be added explicitly.

Importing a file runs its code, so this has the same trust caveat as running
the bots: only put bots you trust in these directories.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from terrabots.battle.agent import BattleAgent

logger = logging.getLogger(__name__)

_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "agents"


@dataclass(frozen=True)
class BotInfo:
    spec: str     # "module:Class"
    name: str
    doc: str      # first line of the class docstring
    source: str   # "yours", "built-in" or "extra"
    droid: bool = False   # battle bots: a Droid (no radar)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _first_doc_line(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    return doc.splitlines()[0] if doc else ""


def _bots_in_module(module_name: str, source: str, base: type) -> list[BotInfo]:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # a broken user bot must not break the setup screen
        logger.warning("Skipping %s: %s", module_name, exc)
        return []
    found = []
    for _, cls in inspect.getmembers(module, inspect.isclass):
        # _Names are helpers (shared base classes), not bots to pick.
        if (issubclass(cls, base) and cls is not base and not cls.__name__.startswith("_")
                and cls.__module__ == module_name and not inspect.isabstract(cls)):
            found.append(BotInfo(f"{module_name}:{cls.__name__}", cls.__name__,
                                 _first_doc_line(cls), source, bool(getattr(cls, "droid", False))))
    return found


def discover_bots(extra_specs: list[str] | None = None,
                  user_dir: str | Path = "bots", base: type = BattleAgent) -> list[BotInfo]:
    """Battle bots by default; pass base=Agent for survival agents."""
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())

    bots: list[BotInfo] = []
    user_dir = Path(user_dir)
    if user_dir.is_dir():
        for path in sorted(user_dir.glob("*.py")):
            if path.stem != "__init__":
                bots += _bots_in_module(f"{user_dir.name}.{path.stem}", "yours", base)
    for path in sorted(_BUILTIN_DIR.glob("*.py")):
        if path.stem != "__init__":
            bots += _bots_in_module(f"terrabots.agents.{path.stem}", "built-in", base)
    # Community submissions: contrib/<author>/<bot>.py (in a checkout of the repo)
    contrib = Path("contrib")
    if contrib.is_dir():
        for path in sorted(contrib.glob("*/*.py")):
            if path.stem != "__init__":
                bots += _bots_in_module(f"contrib.{path.parent.name}.{path.stem}", "community", base)

    known = {b.spec for b in bots}
    for spec in extra_specs or []:
        if spec in known:
            continue
        module_name, _, class_name = spec.partition(":")
        try:
            cls = getattr(importlib.import_module(module_name), class_name)
        except Exception as exc:
            logger.warning("Skipping bot %s: %s", spec, exc)
            continue
        if isinstance(cls, type) and issubclass(cls, base):
            bots.append(BotInfo(spec, class_name, _first_doc_line(cls), "extra",
                                bool(getattr(cls, "droid", False))))
            known.add(spec)
    return bots
