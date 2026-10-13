"""
Pack an offline tournament onto a USB drive. Runs on your laptop (online).

    python tools/airgap/pack.py --config ../mubot/airgap.toml --usb /mnt/e

Downloads the private submissions listed in the config (with your git
credentials), and writes everything the tournament machine needs into
<usb>/terrabots/:

    manifest.json        id, the expected entrants, sha256 of every file
    src.tar              this checkout's committed state (git archive HEAD)
    extras/<package>/    your own closed-source bots (e.g. mubot)
    submissions/<author>/  the downloaded submissions (.py files only)
    runner.py            what the tournament machine runs

Nothing else on the drive is touched; <usb>/terrabots/ is emptied first, so
results of a previous run (written by the tournament machine) never come back
in. A copy of the manifest stays here, in .airgap/, for unpack.py to check the
results against. See docs/airgap.md.

The config is private (it names people's private repositories):

    extra = ["mubot:MuBot@devbyandre"]               # your bots, closed source
    extra_agent = ["mubot:MuBotSurvival@devbyandre"]
    extra_packages = ["../mubot/mubot"]               # copied in; relative to the config
    tournament_args = []                              # e.g. ["--quick"]

    [[submission]]
    author = "alice"                                  # GitHub name; becomes submissions/alice/
    repo = "git@github.com:alice/terrabots-bot.git"   # private repo she shared with you
    folder = "alice"                                  # folder in the repo with the bot (default: author)
    ref = "main"                                      # optional branch or tag
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

AUTHOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
MAX_SUBMISSION_BYTES = 2 * 1024 * 1024
LOCAL = ROOT / ".airgap"          # git-ignored: manifests of packed drives


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg: str) -> None:
    sys.exit(f"pack: {msg}")


def target_dir(usb: Path) -> Path:
    if not usb.is_dir():
        fail(f"{usb} is not a folder (is the drive mounted?)")
    out = usb / "terrabots"
    if out.exists():
        # Only ever empty a folder that is ours.
        if any(out.iterdir()) and not (out / "manifest.json").exists():
            fail(f"{out} exists and isn't a Terrabots drive folder; not touching it")
        shutil.rmtree(out)
    out.mkdir()
    strays = sorted(p.name for p in usb.iterdir() if p.name != "terrabots" and not p.name.startswith("System Volume"))
    if strays:
        print(f"note: other files on the drive ({', '.join(strays[:8])}); a dedicated, freshly formatted "
              "drive is safer")
    return out


def git_archive(dest: Path, uncommitted: bool) -> str:
    """The committed state (HEAD), or with uncommitted=True the working tree's tracked
    and staged changes too (git stash create; untracked files are never included)."""
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    tree = commit
    if dirty and uncommitted:
        tree = subprocess.run(["git", "stash", "create"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip() or commit
    elif dirty:
        print("note: uncommitted changes are not packed (git archive HEAD)")
    with open(dest, "wb") as f:
        subprocess.run(["git", "archive", "--format=tar", tree], cwd=ROOT, stdout=f, check=True)
    return tree


def copy_tree(src: Path, dest: Path, only_py: bool, limit: int | None = None) -> int:
    """Regular files only (no symlinks), no caches. Returns bytes copied."""
    total = 0
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        if any(part == "__pycache__" or part.startswith(".") for part in rel.parts) or p.is_symlink():
            continue
        if p.is_dir() or (only_py and p.suffix != ".py"):
            continue
        total += p.stat().st_size
        if limit is not None and total > limit:
            raise ValueError(f"more than {limit // 1024} KB of code")
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest / rel)
    return total


def download(sub: dict, dest: Path) -> None:
    author = str(sub.get("author", ""))
    if not AUTHOR.match(author):
        raise ValueError(f"author {author!r}: use the GitHub user name")
    folder = str(sub.get("folder", author))
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["git", "-c", "core.symlinks=false", "clone", "--quiet", "--depth", "1", "--no-recurse-submodules"]
        if sub.get("ref"):
            cmd += ["--branch", str(sub["ref"])]
        # Cloning doesn't run anything from the repository; we only read .py files afterwards.
        subprocess.run(cmd + [str(sub["repo"]), tmp + "/repo"], check=True,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        src = (Path(tmp) / "repo" / folder).resolve()
        if not src.is_relative_to((Path(tmp) / "repo").resolve()) or not src.is_dir():
            raise ValueError(f"no folder {folder!r} in {sub['repo']}")
        out = dest / author
        out.mkdir(parents=True)
        copy_tree(src, out, only_py=True, limit=MAX_SUBMISSION_BYTES)
        (out / "__init__.py").touch()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--usb", type=Path, required=True, help="where the drive is mounted, e.g. /mnt/e")
    ap.add_argument("--uncommitted", action="store_true",
                    help="pack uncommitted changes to tracked files too (for testing)")
    a = ap.parse_args()
    cfg = tomllib.loads(a.config.read_text(encoding="utf-8"))
    base = a.config.resolve().parent

    out = target_dir(a.usb)
    commit = git_archive(out / "src.tar", a.uncommitted)

    for pkg in cfg.get("extra_packages", []):
        src = (base / pkg).resolve()
        if not (src / "__init__.py").is_file():
            fail(f"extra package {src} has no __init__.py")
        copy_tree(src, out / "extras" / src.name, only_py=False)

    subs = out / "submissions"
    subs.mkdir()
    for sub in cfg.get("submission", []):
        try:
            download(sub, subs)
            print(f"downloaded {sub['author']}")
        except (subprocess.CalledProcessError, ValueError, KeyError, OSError) as exc:
            print(f"skipping submission {sub.get('author', '?')}: {exc}")
    shutil.copyfile(Path(__file__).with_name("runner.py"), out / "runner.py")

    from tournament import entrants

    bots, agents = entrants(cfg.get("extra", []), cfg.get("extra_agent", []),
                            skip_ours="--skip-ours" in cfg.get("tournament_args", []), submissions=subs)
    for kind, group in (("battle", bots), ("survival", agents)):
        keys = [(e["name"], e["origin"]) for e in group]
        if len(keys) != len(set(keys)):
            fail(f"two {kind} entrants share a name and origin; ask the author to rename one: {keys}")

    files = {str(p.relative_to(out)): sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}
    sandbox = sha256(ROOT / "docker" / "sandbox.Dockerfile")
    manifest = {
        "format": "terrabots-airgap/1", "id": uuid.uuid4().hex, "packed": time.strftime("%Y-%m-%d %H:%M"),
        "commit": commit, "sandbox_dockerfile_sha256": sandbox,
        "extra": cfg.get("extra", []), "extra_agent": cfg.get("extra_agent", []),
        "tournament_args": [str(x) for x in cfg.get("tournament_args", [])],
        "entrants": {"battle": bots, "survival": agents}, "files": files,
    }
    text = json.dumps(manifest, indent=1)
    (out / "manifest.json").write_text(text)
    LOCAL.mkdir(exist_ok=True)
    (LOCAL / f"manifest-{manifest['id']}.json").write_text(text)
    print(f"Packed {len(bots)} battle bots and {len(agents)} survival agents "
          f"({sum(e['run'] == 'sandbox' for e in bots + agents)} sandboxed) onto {out}")
    print("Eject the drive and plug it into the tournament machine.")


if __name__ == "__main__":
    main()
