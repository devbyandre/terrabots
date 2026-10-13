"""
Persistent bot storage: a small data folder per bot class (Robocode's getDataDirectory()).

    stats = self.storage.load("stats", default={})
    stats["battles"] = stats.get("battles", 0) + 1
    self.storage.save("stats", stats)

- One folder per bot class under the battle's data directory (default
  ./bot_data/<module.Class>/), shared by every instance and every battle, so a
  bot can learn across battles.
- JSON only, file names limited to letters, digits, "-", "_" and ".".
- Quota: the folder may hold at most `bot_storage_quota_kb` (BattleConfig,
  default 200 KB like Robocode). A save that would exceed it is refused (save()
  returns False) and the old file stays.
- Without a data directory (e.g. tests, notebooks) storage lives in memory only.

It's a convenience and a fairness rule, not a sandbox: in-process bot code can
still open files itself. Others' bots run in terrabots.battle.sandbox, where
/data is the only writable storage (see docs/sandbox.md).
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class BotStorage:
    def __init__(self, root: str | Path | None, key: str, quota_kb: int = 200) -> None:
        self.key = key
        self.quota_bytes = quota_kb * 1024
        self.directory: Path | None = Path(root) / _safe_dir(key) if root is not None else None
        self._memory: dict[str, str] = {}

    def _path(self, name: str) -> Path:
        if not _NAME.match(name) or name.startswith("."):
            raise ValueError(f"storage name {name!r}: use letters, digits, '-', '_' or '.'")
        assert self.directory is not None
        return self.directory / f"{name}.json"

    def load(self, name: str, default: Any = None) -> Any:
        try:
            if self.directory is None:
                raw = self._memory.get(name)
            else:
                path = self._path(name)
                raw = path.read_text(encoding="utf-8") if path.exists() else None
            return default if raw is None else json.loads(raw)
        except (OSError, ValueError) as exc:
            logger.warning("%s: could not load %r: %s", self.key, name, exc)
            return default

    def save(self, name: str, data: Any) -> bool:
        raw = json.dumps(data, separators=(",", ":"))
        if self.directory is None:
            others = sum(len(v) for k, v in self._memory.items() if k != name)
            if others + len(raw) > self.quota_bytes:
                return self._refuse(name, others + len(raw))
            self._memory[name] = raw
            return True
        path = self._path(name)
        self.directory.mkdir(parents=True, exist_ok=True)
        others = sum(p.stat().st_size for p in self.directory.glob("*.json") if p != path)
        if others + len(raw.encode()) > self.quota_bytes:
            return self._refuse(name, others + len(raw.encode()))
        # Write to a temp file and rename, so a crash never leaves half a file.
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
        os.replace(tmp, path)
        return True

    def used_bytes(self) -> int:
        if self.directory is None:
            return sum(len(v) for v in self._memory.values())
        if not self.directory.exists():
            return 0
        return sum(p.stat().st_size for p in self.directory.glob("*.json"))

    def _refuse(self, name: str, needed: int) -> bool:
        logger.warning("%s: save %r refused, %d bytes > quota %d", self.key, name, needed, self.quota_bytes)
        return False


def _safe_dir(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", key)
