"""
Debug drawing for bots: Robocode's onPaint / graphical debugging.

Inside decide(), draw in arena coordinates (cells); the viewer shows a bot's
drawings when you select it (click the tank) or press D for all bots:

    self.draw.circle(predicted_x, predicted_y, 1.0, color="#ffffff")
    self.draw.line(obs.x, obs.y, target_x, target_y, color="#ff0000")
    self.draw.text(obs.x, obs.y + 2, "locked", color="#ffd166")

The canvas is cleared before every decide(). Shapes are plain data, so they
also cross the process boundary for bots run in subprocesses.
"""

from __future__ import annotations

from typing import Any

MAX_SHAPES = 300  # per bot per tick; keeps a runaway loop from flooding the socket


class DebugCanvas:
    def __init__(self) -> None:
        self.shapes: list[dict[str, Any]] = []

    def clear(self) -> None:
        self.shapes = []

    def _add(self, shape: dict[str, Any]) -> None:
        if len(self.shapes) < MAX_SHAPES:
            self.shapes.append(shape)

    def line(self, x0: float, y0: float, x1: float, y1: float, color: str = "#ffffff") -> None:
        self._add({"k": "line", "x0": round(x0, 3), "y0": round(y0, 3),
                   "x1": round(x1, 3), "y1": round(y1, 3), "c": color})

    def circle(self, x: float, y: float, r: float, color: str = "#ffffff",
               fill: bool = False) -> None:
        self._add({"k": "circle", "x": round(x, 3), "y": round(y, 3), "r": round(r, 3),
                   "c": color, "f": fill})

    def text(self, x: float, y: float, text: str, color: str = "#ffffff") -> None:
        self._add({"k": "text", "x": round(x, 3), "y": round(y, 3), "t": str(text)[:80], "c": color})
