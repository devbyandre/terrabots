"""
Angle and distance helpers, using Robocode's conventions so ported bots keep their math:

- Headings are degrees, 0 = north (+y), 90 = east (+x), increasing clockwise.
- A positive turn is clockwise (Robocode's turnRight).
"""

from __future__ import annotations

import math


def normalize_angle(deg: float) -> float:
    """Map any angle to (-180, 180]. Use for relative bearings and turn amounts."""
    a = math.fmod(deg, 360.0)
    if a <= -180.0:
        a += 360.0
    elif a > 180.0:
        a -= 360.0
    return a


def normalize_heading(deg: float) -> float:
    """Map any angle to [0, 360). Use for absolute headings."""
    a = math.fmod(deg, 360.0)
    return a + 360.0 if a < 0 else a


def heading_to(x0: float, y0: float, x1: float, y1: float) -> float:
    """Absolute heading in [0, 360) from (x0, y0) towards (x1, y1)."""
    return normalize_heading(math.degrees(math.atan2(x1 - x0, y1 - y0)))


def distance(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.hypot(x1 - x0, y1 - y0)


def project(x: float, y: float, heading_deg: float, dist: float) -> tuple[float, float]:
    """Point reached by travelling `dist` from (x, y) along `heading_deg`."""
    rad = math.radians(heading_deg)
    return x + math.sin(rad) * dist, y + math.cos(rad) * dist


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
