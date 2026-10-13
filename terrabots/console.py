"""
Bot consoles: what a bot prints or logs, for the viewer's console panel.

While a bot's code runs (decide() and its hooks), capture() collects:
- print() output,
- lines passed to agent.log(...),
- log records of the bot's own top-level package (e.g. "mybots.*") at INFO and
  above, which then don't also go to the server's terminal.

Lines are capped (MAX_LINES per call, MAX_CHARS per line) so a chatty bot can't
flood the socket. Capture is only switched on for the user's own bots.
"""

from __future__ import annotations

import contextlib
import io
import logging
from typing import Iterator

MAX_LINES = 30
MAX_CHARS = 300


class _ListHandler(logging.Handler):
    def __init__(self, sink: list[str]) -> None:
        super().__init__(logging.INFO)
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self.sink.append(f"[{record.levelname.lower()}] {record.getMessage()}")


class _LineWriter(io.TextIOBase):
    """stdout replacement that turns written text into lines, in order."""

    def __init__(self, sink: list[str]) -> None:
        self.sink, self.buffer = sink, ""

    def write(self, text: str) -> int:
        self.buffer += text
        *done, self.buffer = self.buffer.split("\n")
        self.sink.extend(l for l in done if l.strip())
        return len(text)

    def flush_rest(self) -> None:
        if self.buffer.strip():
            self.sink.append(self.buffer)
        self.buffer = ""


@contextlib.contextmanager
def capture(agent, enabled: bool = True) -> Iterator[list[str]]:
    """Collect the bot's console lines, in the order they happen, into the yielded list."""
    lines: list[str] = []
    if not enabled:
        yield lines
        return
    writer = _LineWriter(lines)
    package = type(agent).__module__.split(".")[0]
    logger = logging.getLogger(package)
    handler = _ListHandler(lines)
    saved = (logger.level, logger.propagate, getattr(agent, "_console", None))
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    agent._console = lines            # self.log() writes straight into the same list
    try:
        with contextlib.redirect_stdout(writer):
            yield lines
    finally:
        writer.flush_rest()
        logger.removeHandler(handler)
        logger.setLevel(saved[0])
        logger.propagate = saved[1]
        agent._console = saved[2] if saved[2] is not None else []
        del lines[MAX_LINES:]
        for i, l in enumerate(lines):
            if len(l) > MAX_CHARS:
                lines[i] = l[:MAX_CHARS] + "…"


def is_users_bot(spec_or_module: str) -> bool:
    """Built-in demo bots live in terrabots.*, community bots in contrib.*;
    everything else is the user's own."""
    return not spec_or_module.startswith(("terrabots.", "contrib."))
