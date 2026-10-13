"""
Bring an offline tournament's results back. Runs on your laptop.

    python tools/airgap/unpack.py --usb /mnt/e

Everything on the drive came back from a machine that ran strangers' code, so
none of it is trusted. Only results/leaderboard.json is read, as JSON, at most
1 MB. It must list exactly the entrants this laptop packed (the manifest copy
in .airgap/, not the one on the drive), with plausible numbers. Names, origins
and descriptions are taken from the laptop's manifest; only the numbers come
from the drive. Then docs/leaderboard.json/.md, the README table and the
website tables are written, for you to review (git diff) and publish.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

LOCAL = ROOT / ".airgap"
MAX_BYTES = 1 << 20
ID = re.compile(r"^[0-9a-f]{32}$")
NUMBERS = {   # per table: field -> (min, max)
    "one_v_one": {"aps": (0, 100), "round_win_pct": (0, 100)},
    "melee": {"share": (0, 10_000), "round_win_pct": (0, 100)},
    "survival": {"avg_lifetime": (0, 1_000_000), "survivors": (0, 1_000_000), "of": (1, 1_000_000)},
}
SETTINGS = {"duel_maps": list, "melee_maps": list, "seeds": int, "duel_rounds": int, "melee_rounds": int,
            "survival_worlds": int, "survival_ticks": int, "quick": bool}


class Rejected(ValueError):
    pass


def printable(text: str, limit: int = 3000) -> str:
    """Untrusted text, safe for a terminal: no control characters (escape sequences)."""
    return "".join(c if c.isprintable() or c == "\n" else "?" for c in text[-limit:])


def check_board(raw: dict, manifest: dict) -> dict:
    if not isinstance(raw, dict):
        raise Rejected("leaderboard.json is not an object")
    settings = raw.get("settings")
    if not isinstance(settings, dict) or set(settings) != set(SETTINGS):
        raise Rejected("settings: unexpected fields")
    for k, t in SETTINGS.items():
        v = settings[k]
        if not isinstance(v, t) or (t is int and (isinstance(v, bool) or not 0 <= v <= 100_000)):
            raise Rejected(f"settings.{k}: unexpected value")
        if t is list and not all(isinstance(m, str) and re.match(r"^[a-z0-9-]{1,40}$", m) for m in v):
            raise Rejected(f"settings.{k}: unexpected map names")
    expected = {"battle": manifest["entrants"]["battle"], "survival": manifest["entrants"]["survival"]}
    board = {"generated": time.strftime("%Y-%m-%d"), "seconds": 0, "settings": settings}
    for table, fields in NUMBERS.items():
        rows = raw.get(table)
        group = expected["survival" if table == "survival" else "battle"]
        if table == "one_v_one" and len(group) < 2:
            group = []
        known = {(e["name"], e["origin"]): e for e in group}
        if not isinstance(rows, list) or len(rows) != len(known):
            raise Rejected(f"{table}: expected {len(known)} rows")
        out = []
        for rank, r in enumerate(rows, 1):
            if not isinstance(r, dict):
                raise Rejected(f"{table}: rows must be objects")
            key = (r.get("name"), r.get("origin"))
            if key not in known:
                raise Rejected(f"{table}: unknown entrant {printable(str(key), 100)}")
            e = known.pop(key)
            row = {"name": e["name"], "spec": "", "origin": e["origin"], "doc": e["doc"]}
            if e["origin"] in ("demo", "template") or e["origin"].startswith("contrib/"):
                row["spec"] = e["spec"]
            for f, (lo, hi) in fields.items():
                v = r.get(f)
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
                    raise Rejected(f"{table}: {e['name']}.{f} is not a plausible number")
                row[f] = v
            row["rank"] = rank
            out.append(row)
        board[table] = out
    return board


def main() -> None:
    ap = argparse.ArgumentParser(description="Check and import an offline tournament's results.")
    ap.add_argument("--usb", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "docs")
    a = ap.parse_args()
    drive = a.usb / "terrabots"
    try:
        drive_id = json.loads((drive / "manifest.json").read_text(encoding="utf-8")[:MAX_BYTES]).get("id", "")
        if not isinstance(drive_id, str) or not ID.match(drive_id):
            raise Rejected("the drive's manifest id is malformed")
        local = LOCAL / f"manifest-{drive_id}.json"
        if not local.is_file():
            raise Rejected("this drive wasn't packed on this laptop (no matching manifest in .airgap/)")
        manifest = json.loads(local.read_text(encoding="utf-8"))
        status_file = drive / "results" / "status.json"
        if status_file.is_file() and status_file.stat().st_size < 10_000:
            status = json.loads(status_file.read_text(encoding="utf-8", errors="replace"))
            if isinstance(status, dict) and status.get("ok") is False:
                raise Rejected(f"the tournament failed: {printable(str(status.get('error')), 500)}")
        path = drive / "results" / "leaderboard.json"
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise Rejected("no results/leaderboard.json (or too big)")
        board = check_board(json.loads(path.read_text(encoding="utf-8")), manifest)
    except (Rejected, ValueError, OSError, KeyError) as exc:
        sys.exit(f"unpack: rejected: {exc}")

    from tournament import markdown, update_snapshots

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "leaderboard.json").write_text(json.dumps(board, indent=1) + "\n")
    (a.out / "leaderboard.md").write_text(markdown(board))
    if a.out.resolve() == (ROOT / "docs").resolve():
        update_snapshots(board)
    log = drive / "results" / "log.txt"
    if log.is_file():
        print("Last lines of the tournament log (from the drive):")
        print(printable(log.read_text(encoding="utf-8", errors="replace"), 1500))
    print(f"\nImported results for {sum(len(board[t]) for t in NUMBERS)} rows into {a.out}.")
    print("Review with `git diff`, then: git add docs/leaderboard.* README.md docs/index.html && "
          "git commit -m 'Update leaderboard' && git push")
    print("Then reformat the drive before its next use.")


if __name__ == "__main__":
    main()
