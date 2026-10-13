"""
Run a packed tournament on the offline tournament machine (see docs/airgap.md).

    python3 runner.py --usb /run/terrabots-usb

Started by the machine's trigger when the drive is plugged in; it can also be run
by hand, or on a laptop for a test. It:
1. checks every packed file against the manifest (a damaged drive stops here),
2. checks that the sandbox image was built from the same Dockerfile,
3. unpacks into a work folder in RAM, runs tools/tournament.py there (submitted
   bots sandboxed, your extras in-process),
4. writes results/ on the drive: leaderboard.json, log.txt, status.json.

A drive that already has results for its manifest is left alone, so leaving the
drive in across a reboot doesn't run the tournament twice. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

LOG_LIMIT = 200 * 1024
IMAGE = "terrabots-sandbox"
LABEL = "terrabots.dockerfile.sha256"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_status(results: Path, **fields) -> None:
    results.mkdir(exist_ok=True)
    (results / "status.json").write_text(json.dumps(fields, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a packed Terrabots tournament.")
    ap.add_argument("--usb", type=Path, required=True, help="where the drive is mounted")
    ap.add_argument("--work", type=Path, default=None, help="work folder (default: a temporary one)")
    ap.add_argument("--python", default=sys.executable, help="Python with numpy, for the tournament")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()

    drive = a.usb / "terrabots"
    results = drive / "results"
    manifest = json.loads((drive / "manifest.json").read_text())
    if (results / "status.json").exists():
        done = json.loads((results / "status.json").read_text())
        if done.get("manifest") == manifest["id"]:
            print("This drive's tournament has already run; nothing to do.")
            return 0
    started = time.time()

    def stop(reason: str) -> int:
        write_status(results, manifest=manifest["id"], ok=False, error=reason)
        print(f"runner: {reason}", file=sys.stderr)
        return 1

    for rel, digest in manifest["files"].items():
        p = drive / rel
        if not p.is_file() or sha256(p) != digest:
            return stop(f"{rel} is missing or damaged; pack the drive again")
    label = subprocess.run(["docker", "image", "inspect", "-f", f'{{{{index .Config.Labels "{LABEL}"}}}}', IMAGE],
                           capture_output=True, text=True).stdout.strip()
    if label != manifest["sandbox_dockerfile_sha256"]:
        return stop("the sandbox image doesn't match this version's docker/sandbox.Dockerfile; "
                    "rebuild the tournament machine's image (docs/airgap.md)")

    work = a.work or Path(tempfile.mkdtemp(prefix="terrabots-"))
    if work.exists():
        shutil.rmtree(work)
    src = work / "src"
    src.mkdir(parents=True)
    with tarfile.open(drive / "src.tar") as tar:
        try:
            tar.extractall(src, filter="data")
        except TypeError:     # Python before 3.11.4 (Raspberry Pi OS); the archive is our own git archive
            tar.extractall(src)
    shutil.copytree(drive / "submissions", src / "submissions")
    if (drive / "extras").is_dir():
        shutil.copytree(drive / "extras", work / "extras")
    else:
        (work / "extras").mkdir()
    # The sandbox runs bots as an unprivileged user, which needs to read their files.
    for p in [work, *work.rglob("*")]:
        p.chmod(0o755 if p.is_dir() else 0o644)

    cmd = [a.python, "tools/tournament.py", "--out", str(work / "out"), "--workers", str(a.workers)]
    cmd += [f"--extra={e}" for e in manifest["extra"]] + [f"--extra-agent={e}" for e in manifest["extra_agent"]]
    cmd += manifest["tournament_args"]
    env = {**os.environ, "PYTHONPATH": f"{work / 'extras'}{os.pathsep}{src}"}
    print("running:", " ".join(cmd))
    with open(work / "log.txt", "wb") as log:
        code = subprocess.run(cmd, cwd=src, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    results.mkdir(exist_ok=True)
    data = (work / "log.txt").read_bytes()
    (results / "log.txt").write_bytes(data[-LOG_LIMIT:])
    board = work / "out" / "leaderboard.json"
    if code != 0 or not board.is_file():
        return stop(f"the tournament failed (exit code {code}); see results/log.txt")
    shutil.copyfile(board, results / "leaderboard.json")
    write_status(results, manifest=manifest["id"], ok=True, seconds=round(time.time() - started))
    if a.work is None:
        shutil.rmtree(work, ignore_errors=True)
    print(f"Done in {round(time.time() - started)} s; results are on the drive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
