"""
Compare Terrabots with real Robocode, tick by tick.

    python tools/robocode_conformance/conformance.py            # probe scenario
    python tools/robocode_conformance/conformance.py --duel     # two Duelists fighting

Downloads Robocode (EPL, from its GitHub releases) into a cache folder the first
time, runs a probe bot of ours in it headless (Java 17 in Docker, since Robocode
needs a security manager), runs the same bot in Terrabots through the Robocode
adapter from the same start positions, and diffs the per-tick logs the probe
writes: position, headings, velocity, energy, gun heat, scans, bullet events.

Needs Docker, javac, and the terrabots-sandbox-robocode image. Results so far
(Robocode 1.11.1): the probe scenario matches exactly (0 differences in 1416
records). Duels diverge once two bullets resolve in the same tick, because
Robocode processes bullets in random order; the rules themselves agree.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
VERSION = "1.11.1"
URL = f"https://github.com/robo-code/robocode/releases/download/v{VERSION}/robocode-{VERSION}-setup.jar"
CACHE = ROOT / ".cache" / "robocode-conformance"
FIELD = (800, 592)          # 50 x 37 cells at 16 px per cell
SCENARIOS = {
    "probe": {"bots": ["tbprobe.Probe", "sample.SittingDuck"], "start": [(200, 150, 30), (600, 400, 0)]},
    "duel": {"bots": ["tbprobe.Duelist", "tbprobe.Duelist"], "start": [(150, 300, 90), (650, 320, 270)]},
}


def robocode_home() -> Path:
    home = CACHE / f"robocode-{VERSION}"
    if not (home / "libs" / "robocode.jar").exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        setup = CACHE / "setup.jar"
        print(f"downloading Robocode {VERSION} ...")
        urllib.request.urlretrieve(URL, setup)
        with zipfile.ZipFile(setup) as z:
            z.extractall(home)
        (home / "config").mkdir(exist_ok=True)
        # A generous time per turn: a skipped turn on the Robocode side would show as a difference.
        (home / "config" / "robocode.properties").write_text("robocode.cpu.constant=2000000000\n")
    return home


def build_probes(out: Path) -> Path:
    classes = out / "classes"
    shutil.rmtree(classes, ignore_errors=True)
    sources = [str(p) for p in (ROOT / "adapters/robocode/src").rglob("*.java")]
    sources += [str(p) for p in (HERE / "src").rglob("*.java")]
    subprocess.run(["javac", "--release", "17", "-Xlint:-options", "-d", str(classes), *sources], check=True)
    stage = out / "probes"
    shutil.rmtree(stage, ignore_errors=True)
    (stage / "tbprobe").mkdir(parents=True)
    for f in (classes / "tbprobe").glob("*.class"):
        shutil.copy(f, stage / "tbprobe")
    for f in (HERE / "src" / "tbprobe").glob("*.properties"):
        shutil.copy(f, stage / "tbprobe")
    jar = out / "tbprobe.jar"
    subprocess.run(["jar", "--create", "--file", str(jar), "-C", str(stage), "."], check=True)
    return jar


def run_real(home: Path, jar: Path, scenario: dict) -> dict[int, str]:
    robots = home / "robots"
    shutil.copy(jar, robots / "tbprobe.jar")
    (robots / "robot.database").unlink(missing_ok=True)
    shutil.rmtree(robots / ".data" / "tbprobe", ignore_errors=True)
    positions = ",".join(f"({x},{y},{h})" for x, y, h in scenario["start"])
    (home / "conformance.battle").write_text(
        f"robocode.battleField.width={FIELD[0]}\nrobocode.battleField.height={FIELD[1]}\n"
        "robocode.battle.numRounds=1\nrobocode.battle.gunCoolingRate=0.1\n"
        "robocode.battle.rules.inactivityTime=450\nrobocode.battle.hideEnemyNames=false\n"
        f"robocode.battle.selectedRobots={','.join(scenario['bots'])}\n"
        f"robocode.battle.initialPositions={positions}\n")
    opens = ["--add-opens=java.base/sun.net.www.protocol.jar=ALL-UNNAMED",
             "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED",
             "--add-opens=java.desktop/javax.swing.text=ALL-UNNAMED", "--add-opens=java.desktop/sun.awt=ALL-UNNAMED"]
    import os
    subprocess.run(["docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
                    "-e", "HOME=/tmp", "-v", f"{home}:/rc", "-w", "/rc", "eclipse-temurin:17-jdk",
                    "java", "-Xmx512M", "-cp", "libs/*", "-XX:+IgnoreUnrecognizedVMOptions", *opens,
                    "robocode.Robocode", "-battle", "/rc/conformance.battle", "-nodisplay", "-nosound",
                    "-results", "/rc/results.txt"], check=True, capture_output=True)
    logs = {}
    for f in (robots / ".data" / "tbprobe").rglob("*.log"):
        digits = re.sub(r"\D", "", f.stem)
        logs[int(digits[-1]) if len(digits) > 1 else 1] = f.read_text()
    return logs


def run_ours(jar: Path, scenario: dict) -> dict[int, str]:
    import terrabots.battle.sandbox as sb
    from terrabots.agents.sitting_duck import SittingDuck
    from terrabots.battle import BattleConfig, BattleRunner
    from terrabots.battle.sandbox import JarEntry

    def drain(self):   # keep all of the probes' output
        for chunk in iter(lambda: self.proc.stderr.read(4096), b""):
            self._stderr.append(chunk)
    sb._Channel._drain = drain
    entries = {e.class_name: e for e in JarEntry.from_jar(jar)}
    bots = [(entries[b.split(".")[-1]], 1) if b.startswith("tbprobe.") else (SittingDuck, 1) for b in scenario["bots"]]
    cfg = BattleConfig(rounds=1, seed=1, terrain="flat", width=FIELD[0] // 16, height=FIELD[1] // 16,
                       hit_energy_return="robocode", max_ticks_per_round=5000)
    runner = BattleRunner(cfg, bots, time_budget_ms=None)
    arena = runner.start_round()
    for bid, (x, y, h) in enumerate(scenario["start"]):
        b = arena.slots[bid].body
        b.x, b.y, b.heading, b.gun_heading, b.radar_heading, b.radar_prev = x / 16, y / 16, h, h, h, h
    while not arena.over:
        runner.step()
    runner.end_round()
    remote = dict(runner.remote)
    runner.close()
    logs, index = {}, 0
    for bid in sorted(remote):
        index += 1
        text = b"".join(remote[bid]._ch._stderr).decode("utf-8", "replace")
        logs[index] = "\n".join(dict.fromkeys(l for l in text.splitlines() if l.startswith("P "))) + "\n"
    return logs


def parse(text: str) -> dict[tuple[int, str], dict[str, str]]:
    out = {}
    for line in text.splitlines():
        m = re.match(r"P (\d+) (.*)", line.strip())
        if not m:
            continue
        rest = m.group(2)
        kind = rest.split()[0] if "=" not in rest.split()[0] else "state"
        out.setdefault((int(m.group(1)), kind), dict(kv.split("=", 1) for kv in rest.split() if "=" in kv))
    return out


def diff(real: str, ours: str, tolerance: float = 0.01) -> list[tuple]:
    a, b = parse(real), parse(ours)
    found = []
    for key in sorted(set(a) | set(b)):
        x, y = a.get(key), b.get(key)
        if x is None or y is None:
            found.append((key, "only Robocode" if x is not None else "only Terrabots"))
            continue
        for k, v in x.items():
            try:
                if k in y and abs(float(v) - float(y[k])) > tolerance:
                    found.append((key, k, v, y[k]))
            except ValueError:
                if y.get(k) != v:
                    found.append((key, k, v, y.get(k)))
    return found


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare Terrabots with real Robocode, tick by tick.")
    ap.add_argument("--duel", action="store_true", help="two Duelists instead of the probe vs SittingDuck")
    a = ap.parse_args()
    scenario = SCENARIOS["duel" if a.duel else "probe"]
    home = robocode_home()
    jar = build_probes(CACHE)
    real, ours = run_real(home, jar, scenario), run_ours(jar, scenario)
    for i in sorted(real):
        d = diff(real[i], ours.get(i, ""))
        print(f"bot {i}: {len(d)} differences in {len(parse(real[i]))} Robocode records")
        for row in d[:12]:
            print("  ", row)


if __name__ == "__main__":
    main()
