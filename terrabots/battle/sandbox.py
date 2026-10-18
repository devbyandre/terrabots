"""
Run bots you don't trust: each one in its own locked-down Docker container.

    from terrabots.battle.sandbox import SandboxEntry
    BattleRunner(config, [(SandboxEntry("submissions.alice.bot:Rammer"), 1), (Tracker, 1)])

What the container allows (see docker_command()):
- no network, a read-only filesystem, 16 MB of scratch space in /tmp, no
  Docker log files (a bot printing gigabytes can't fill your disk),
- bot storage in a size-limited /data that disappears with the container,
- 512 MB of memory, one CPU, 64 processes, no Linux capabilities, an
  unprivileged user, no privilege escalation,
- only two folders from your machine, both read-only: the engine's own
  `terrabots` package (public code) and the bot's own folder. Never other bots.

What the engine trusts: nothing the bot sends. The bot's module is never
imported on the host (classes are found by reading the source, see find_bots()),
messages are JSON (no pickle), and every reply is checked (terrabots.battle.wire).
A bot that answers late is skipped; one that answers too late, too much or
garbage is stopped. A bot's own movement profile is ignored: sandboxed bots use
the standard one, so nobody can give themselves a higher climb limit.

The sandbox image only holds Python and numpy (docker/sandbox.Dockerfile):

    docker build -t terrabots-sandbox -f docker/sandbox.Dockerfile docker/

Cost: a container takes ~0.5 s to start and a turn's round trip is ~1 ms, so
sandboxed battles run slower than in-process ones (see docs).
"""

from __future__ import annotations

import ast
import json
import logging
import queue
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import terrabots
from terrabots.battle import wire
from terrabots.battle.actions import BattleAction
from terrabots.battle.isolation import BotProcessError, RemoteBot
from terrabots.battle.observation import BattleObservation
from terrabots.framework.agent import Agent
from terrabots.world_terrain import WorldGrid

logger = logging.getLogger(__name__)

IMAGE = "terrabots-sandbox"
ROBOCODE_IMAGE = "terrabots-sandbox-robocode"   # Java + adapters/robocode, for Robocode jars
GROUP_ROOTS = ("contrib", "submissions")   # <root>/<author>/<bot>.py: one author's folder each
START_TIMEOUT_S = 60.0
HARD_TIMEOUT_MIN_S = 2.0
PIPE_ALLOWANCE_MS = 5.0       # a round trip's own cost, not counted against the bot
BOT_UID = 10001


class SandboxError(RuntimeError):
    """The sandbox can't be used (no Docker, no image, bad bot path)."""


@dataclass(frozen=True)
class SandboxEntry:
    """A bot to run sandboxed: its spec and the folder its module path starts in."""
    spec: str
    root: Path = field(default_factory=Path.cwd)

    @property
    def module(self) -> str:
        return self.spec.partition(":")[0]

    @property
    def class_name(self) -> str:
        return self.spec.partition(":")[2]


@dataclass(frozen=True)
class JarEntry(SandboxEntry):
    """A Robocode bot: a jar from the Robocode world (e.g. the RoboRumble), run
    unchanged through the Terrabots adapter (adapters/robocode). Make them with
    JarEntry.from_jar(path), which reads the robot class from the jar."""
    jar: Path = Path()

    @property
    def class_name(self) -> str:
        return self.spec.partition(":")[2].rpartition(".")[2]

    @staticmethod
    def from_jar(path: str | Path) -> list["JarEntry"]:
        """The robots a jar declares in its .properties files (robot.classname=...)."""
        import zipfile

        path = Path(path).resolve()
        if path.is_symlink() or not path.is_file():
            raise SandboxError(f"{path}: not a jar file")
        found = []
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if not info.filename.endswith(".properties") or info.file_size > 64 * 1024:
                    continue
                for line in z.read(info).decode("latin-1").splitlines():
                    key, _, value = line.partition("=")
                    if key.strip() == "robot.classname":
                        cls = value.strip()
                        if all(part.isidentifier() for part in cls.split(".")):
                            found.append(JarEntry(f"robocode:{cls}", path.parent, path))
        return found


# ---------------------------------------------------------------------------
# Setup checks and the docker command
# ---------------------------------------------------------------------------

def check_available(image: str = IMAGE) -> None:
    """Raise SandboxError with a helpful message unless Docker and the image are there."""
    if shutil.which("docker") is None:
        raise SandboxError("sandboxed bots need Docker (docker not found)")
    r = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    if r.returncode != 0:
        how = ("-f docker/sandbox-robocode.Dockerfile adapters/robocode/" if image == ROBOCODE_IMAGE
               else "-f docker/sandbox.Dockerfile docker/")
        raise SandboxError(f"sandbox image {image!r} missing; build it with: docker build -t {image} {how}")
    # Without kernel support Docker accepts --memory / --pids-limit and silently
    # ignores them (Raspberry Pi OS ships like that), so check instead of trusting.
    r = subprocess.run(["docker", "info", "--format", "{{.MemoryLimit}} {{.PidsLimit}}"],
                       capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.split() != ["true", "true"]:
        raise SandboxError("Docker can't enforce memory and process limits here, so the sandbox "
                           "won't run. On a Raspberry Pi add 'cgroup_enable=memory cgroup_memory=1' to "
                           "/boot/firmware/cmdline.txt and reboot")


def bot_mount(entry: SandboxEntry) -> tuple[Path, str]:
    """(folder or file on the host, path in the container) holding the bot's code.

    For <contrib|submissions>/<author>/... it's that author's folder; otherwise
    the module's top-level package (or single file). Symlinks are refused, so a
    submission can't point its folder at someone else's code."""
    parts = entry.module.split(".")
    if not all(p.isidentifier() for p in parts) or not entry.class_name.isidentifier():
        raise SandboxError(f"{entry.spec!r}: not a 'module:Class' spec")
    rel = parts[:2] if parts[0] in GROUP_ROOTS and len(parts) >= 3 else parts[:1]
    root = Path(entry.root).resolve()
    host = root.joinpath(*rel)
    if not host.is_dir():
        host = host.with_suffix(".py")
        if len(rel) != len(parts) or not host.is_file():
            raise SandboxError(f"{entry.spec!r}: no {'/'.join(rel)}/ folder or .py file in {root}")
    p = root
    for part in host.relative_to(root).parts:
        p = p / part
        if p.is_symlink():
            raise SandboxError(f"{entry.spec!r}: {p} is a symlink; sandboxed bots can't use them")
    return host, "/bot/" + "/".join(host.relative_to(root).parts)


def docker_command(entry: SandboxEntry, name: str, quota_kb: int = 200, image: str = IMAGE) -> list[str]:
    # RoboRumble clients give Java bots 512 MB of heap; strong bots collect a lot of
    # statistics across rounds and stall (garbage collection) with less.
    memory = "1g" if isinstance(entry, JarEntry) else "512m"
    locked = [
        "docker", "run", "--rm", "-i", "--name", name,
        "--network", "none", "--read-only", "--ipc", "none", "--log-driver", "none",
        "--tmpfs", "/tmp:rw,size=16m,mode=1777",
        "--tmpfs", f"/data:rw,size={quota_kb + 64}k,uid={BOT_UID},gid={BOT_UID},mode=700",
        "--memory", memory, "--memory-swap", memory, "--cpus", "1", "--pids-limit", "64",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", f"{BOT_UID}:{BOT_UID}",
    ]
    if isinstance(entry, JarEntry):
        # Only the jar itself goes in; the adapter is part of the image.
        jar = Path(entry.jar).resolve()
        if Path(entry.jar).is_symlink() or not jar.is_file():
            raise SandboxError(f"{entry.jar}: not a jar file")
        return locked + ["-v", f"{jar}:/bot/bot.jar:ro", ROBOCODE_IMAGE,
                         "java", "-Xmx512m", "-XX:+UseSerialGC", "-XX:-UsePerfData",
                         "-cp", "/opt/terrabots/adapter.jar:/bot/bot.jar", "terrabots.robocode.Host"]
    host, inside = bot_mount(entry)
    engine = Path(terrabots.__file__).resolve().parent
    return locked + ["-v", f"{engine}:/engine/terrabots:ro", "-v", f"{host}:{inside}:ro",
                     image, "python", "-m", "terrabots.battle.sandbox_child"]


# ---------------------------------------------------------------------------
# One container and its JSON pipe
# ---------------------------------------------------------------------------

class _Channel:
    def __init__(self, entry: SandboxEntry, quota_kb: int, label: str) -> None:
        self.label = label
        self.name = f"terrabots-{uuid.uuid4().hex[:12]}"
        self.dead = False
        self._replies: queue.Queue = queue.Queue()
        self._stderr: list[bytes] = []
        self.proc = subprocess.Popen(docker_command(entry, self.name, quota_kb), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._drain, daemon=True).start()

    def _read(self) -> None:
        out = self.proc.stdout
        while True:
            line = out.readline(wire.MAX_LINE_BYTES + 1)
            if not line:
                self._replies.put(None)
                return
            if len(line) > wire.MAX_LINE_BYTES:
                self._replies.put(wire.WireError("reply too long"))
                return
            self._replies.put(line.decode("utf-8", "replace"))

    def _drain(self) -> None:
        # Keep the last few KB of stderr (crash reports); the rest is dropped.
        for chunk in iter(lambda: self.proc.stderr.read(4096), b""):
            self._stderr = (self._stderr + [chunk])[-4:]

    def stderr_tail(self) -> str:
        return b"".join(self._stderr).decode("utf-8", "replace")[-2000:]

    def send(self, msg: dict[str, Any]) -> None:
        if self.dead:
            return
        try:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode())
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self.kill("pipe closed")

    def recv(self, timeout: float, what: str) -> dict[str, Any]:
        if self.dead:
            raise BotProcessError(f"{self.label}: container is gone")
        try:
            item = self._replies.get(timeout=max(0.0, timeout))
        except queue.Empty:
            self.kill(f"no answer to {what} within {timeout:.1f}s")
            raise BotProcessError(f"{self.label}: no answer to {what} within {timeout:.1f}s; stopped") from None
        if item is None:
            self.kill("exited")
            raise BotProcessError(f"{self.label}: container exited\n{self.stderr_tail()}")
        try:
            if isinstance(item, Exception):
                raise item
            return wire.parse_line(item)
        except wire.WireError as exc:
            self.kill(str(exc))
            raise BotProcessError(f"{self.label}: {exc}; stopped") from None

    def kill(self, reason: str) -> None:
        if not self.dead:
            logger.warning("Stopping sandboxed %s: %s", self.label, reason)
        self.dead = True
        subprocess.run(["docker", "kill", self.name], capture_output=True, timeout=30)
        if self.proc.poll() is None:
            self.proc.kill()

    def close(self) -> None:
        if not self.dead:
            self.send({"t": "stop"})
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        self.dead = True
        if self.proc.poll() is None:      # didn't stop when asked
            subprocess.run(["docker", "kill", self.name], capture_output=True, timeout=30)
            self.proc.kill()


def _start(entry: SandboxEntry, mode: str, world: WorldGrid | None, seed: int | None,
           quota_kb: int, label: str) -> tuple[_Channel, bool]:
    ch = _Channel(entry, quota_kb, label)
    ch.send({"t": "start", "mode": mode, "spec": entry.spec, "seed": seed, "quota_kb": quota_kb,
             "world": wire.world_out(world) if world is not None else None})
    reply = ch.recv(START_TIMEOUT_S, "start")
    if reply.get("t") != "ready":
        msg = str(reply.get("msg", ""))[:2000]
        ch.close()
        raise BotProcessError(f"{label} failed to load:\n{msg}")
    return ch, bool(reply.get("droid") is True)


# ---------------------------------------------------------------------------
# Battle bots
# ---------------------------------------------------------------------------

class SandboxBot(RemoteBot):
    """Arena-facing proxy for a battle bot in its own container."""

    def __init__(self, entry: SandboxEntry, world: WorldGrid, seed: int | None, quota_kb: int = 200) -> None:
        super().__init__()
        self.spec = entry.spec
        self.class_name = entry.class_name
        self._restart = (entry, world, seed, quota_kb)
        self._ch, self.droid = _start(entry, "battle", world, seed, quota_kb, entry.spec)
        # Java bots warm up (JIT) and often precompute on their first turn; Robocode
        # skips their turns rather than stopping them, so they get more headroom.
        java = isinstance(entry, JarEntry)
        self.first_turn_s = 30.0 if java else HARD_TIMEOUT_MIN_S
        self.turn_s = 5.0 if java else HARD_TIMEOUT_MIN_S
        self._first = True
        self._seq = 0
        self._t0 = 0.0
        self.last_elapsed_ms = 0.0
        self.last_console: list[str] = []
        self.console = False

    @property
    def is_dead(self) -> bool:
        return self._ch.dead

    def on_round_start(self, round_number: int, rounds: int) -> None:
        if self._ch.dead:
            # Stopped last round (hung, crashed, too much output): a fresh container,
            # so one bad round doesn't cost the whole battle. Its memory is lost.
            entry, world, seed, quota_kb = self._restart
            self._ch, self.droid = _start(entry, "battle", world, seed, quota_kb, entry.spec)
        self._ch.label = self.name
        self._first = True
        self._ch.send({"t": "round", "bot_id": self.bot_id, "name": self.name, "rules": self.rules.to_dict(),
                       "round": round_number, "rounds": rounds, "team": self.team, "leader": self.is_leader,
                       "teammates": {str(k): v for k, v in self.teammates.items()}})
        reply = self._ch.recv(START_TIMEOUT_S, "on_round_start")
        try:
            if reply.get("t") != "ok":
                raise wire.WireError(str(reply.get("msg", "no ok"))[:2000])
            self.adjust_gun_for_body_turn = wire.flag(reply.get("adj_gun"), "adj_gun")
            self.adjust_radar_for_gun_turn = wire.flag(reply.get("adj_radar"), "adj_radar")
            self.colors = wire.colors_in(reply.get("colors", {}))
            self.plain_robot = wire.flag(reply.get("plain_robot", False), "plain_robot")
        except wire.WireError as exc:
            raise BotProcessError(f"{self.name} failed in on_round_start: {exc}") from None

    def on_death(self) -> None:
        self._ch.send({"t": "death"})

    def on_round_end(self, won: bool) -> None:
        self._ch.send({"t": "round_end", "won": won})

    def request_decide(self, obs: BattleObservation) -> None:
        if self._ch.dead:
            return
        self._seq += 1
        self._t0 = time.perf_counter()
        self._ch.send({"t": "decide", "seq": self._seq, "obs": wire.battle_obs_out(obs), "console": self.console})

    def collect_decide(self, budget_ms: float | None) -> BattleAction:
        hard = self.first_turn_s if self._first else self.turn_s
        self._first = False
        deadline = self._t0 + max(hard, 20 * (budget_ms or 0) / 1000)
        while True:
            reply = self._ch.recv(deadline - time.perf_counter(), "decide")
            if reply.get("seq") != self._seq:
                continue     # a late answer to a turn we already gave up on
            if reply.get("t") == "decide_error":
                raise BotProcessError(str(reply.get("msg", ""))[:2000])
            try:
                action = wire.battle_action_in(reply.get("action"))
                self.draw.shapes = wire.shapes_in(reply.get("shapes", []))
                self._outbox = wire.outbox_in(reply.get("outbox", []))
                self.last_console = wire.console_in(reply.get("console", []))
                self.adjust_gun_for_body_turn = wire.flag(reply.get("adj_gun"), "adj_gun")
                self.adjust_radar_for_gun_turn = wire.flag(reply.get("adj_radar"), "adj_radar")
                reported = wire.number(reply.get("elapsed_ms", 0.0), "elapsed_ms")
            except wire.WireError as exc:
                self._outbox = []
                raise BotProcessError(f"{self.name}: {exc}") from None
            # The bot's own timing can't be trusted further than the wall clock says.
            wall = (time.perf_counter() - self._t0) * 1000
            self.last_elapsed_ms = max(reported, wall - PIPE_ALLOWANCE_MS)
            return action

    def close(self) -> None:
        self._ch.close()


def start_sandboxed(entries: list[tuple[int, SandboxEntry]], world: WorldGrid, seed: int | None,
                    quota_kb: int) -> dict[int, SandboxBot]:
    """Start one container per bot id, in parallel."""
    check_available()
    if any(isinstance(e, JarEntry) for _, e in entries):
        check_available(ROBOCODE_IMAGE)
    out: dict[int, SandboxBot] = {}
    errors: list[Exception] = []

    def start(bid: int, entry: SandboxEntry) -> None:
        try:
            out[bid] = SandboxBot(entry, world, None if seed is None else seed + bid, quota_kb)
        except Exception as exc:  # reported after all have tried
            errors.append(exc)

    threads = [threading.Thread(target=start, args=e) for e in entries]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        for b in out.values():
            b.close()
        raise errors[0]
    return out


# ---------------------------------------------------------------------------
# Survival agents
# ---------------------------------------------------------------------------

class SandboxAgent(Agent):
    """Simulation-facing proxy for a survival agent in its own container.
    Make them with SandboxAgent.factory(entry) and pass that to Simulation.add_agent."""

    def __init__(self, entry: SandboxEntry, seed: int | None = None) -> None:
        super().__init__()
        self.class_name = entry.class_name
        self._ch, _ = _start(entry, "survival", None, seed, 0, entry.spec)
        self._seq = 0
        self.last_console: list[str] = []

    @staticmethod
    def factory(entry: SandboxEntry, seed: int | None = None):
        count = iter(range(1_000_000))
        return lambda: SandboxAgent(entry, None if seed is None else seed + next(count))

    def on_birth(self) -> None:
        self._ch.send({"t": "birth", "agent_id": self.agent_id, "pos": list(self.pos), "energy": self.energy})
        reply = self._ch.recv(START_TIMEOUT_S, "on_birth")
        if reply.get("t") != "ok":
            raise BotProcessError(f"{self.class_name} failed in on_birth: {str(reply.get('msg', ''))[:2000]}")

    def on_message(self, sender_id: int, kind: str, payload: dict) -> None:
        """Replayed inside the container from obs.inbox, right before decide()."""

    def on_death(self) -> None:
        self._ch.send({"t": "death"})

    def request_decide(self, obs) -> None:
        if self._ch.dead:
            return
        self._seq += 1
        self._t0 = time.perf_counter()
        self._ch.send({"t": "decide", "seq": self._seq, "obs": wire.survival_obs_out(obs)})

    def collect_decide(self):
        from terrabots.framework.actions import Action, MoveDirection

        if self._ch.dead:
            return Action(move_direction=MoveDirection.STAY)
        try:
            while True:
                reply = self._ch.recv(self._t0 + HARD_TIMEOUT_MIN_S - time.perf_counter(), "decide")
                if reply.get("seq") == self._seq:
                    break
            if reply.get("t") == "decide_error":
                logger.warning("%s raised in decide():\n%s", self.class_name, str(reply.get("msg", ""))[:2000])
                return Action(move_direction=MoveDirection.STAY)
            self.last_console = wire.console_in(reply.get("console", []))
            return wire.survival_action_in(reply.get("action"))
        except (BotProcessError, wire.WireError) as exc:
            logger.warning("%s: %s", self.class_name, exc)
            return Action(move_direction=MoveDirection.STAY)

    def decide(self, obs):
        self.request_decide(obs)
        return self.collect_decide()

    def close(self) -> None:
        self._ch.close()


# ---------------------------------------------------------------------------
# Finding bots without running them
# ---------------------------------------------------------------------------

BATTLE_BASES = {"BattleAgent", "AdvancedRobot", "TeamRobot"}
SURVIVAL_BASES = {"Agent"}


@dataclass(frozen=True)
class FoundBot:
    spec: str
    name: str
    doc: str
    kind: str          # "battle" or "survival"
    droid: bool


def find_bots(path: Path, module: str) -> list[FoundBot]:
    """Bot classes in a source file, found by reading it (never importing it).

    A class counts if it subclasses BattleAgent / AdvancedRobot / TeamRobot
    (battle) or Agent (survival), directly or through another class in the same
    file. Names starting with "_" are helpers and skipped."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, ValueError) as exc:
        logger.warning("Skipping %s: %s", path, exc)
        return []
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

    def base_names(node: ast.ClassDef) -> set[str]:
        return {b.id if isinstance(b, ast.Name) else b.attr for b in node.bases
                if isinstance(b, (ast.Name, ast.Attribute))}

    def kind_of(name: str, seen: frozenset = frozenset()) -> str | None:
        node = classes.get(name)
        if node is None or name in seen:
            return None
        for b in base_names(node):
            if b in BATTLE_BASES:
                return "battle"
            if b in SURVIVAL_BASES:
                return "survival"
            k = kind_of(b, seen | {name})
            if k:
                return k
        return None

    def is_droid(name: str, seen: frozenset = frozenset()) -> bool:
        node = classes.get(name)
        if node is None or name in seen:
            return False
        for stmt in node.body:
            if (isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "droid" for t in stmt.targets)
                    and isinstance(stmt.value, ast.Constant)):
                return stmt.value.value is True
        return "Droid" in base_names(node) or any(is_droid(b, seen | {name}) for b in base_names(node))

    found = []
    for name, node in classes.items():
        kind = kind_of(name)
        if kind is None or name.startswith("_"):
            continue
        doc = (ast.get_docstring(node) or "").splitlines()
        found.append(FoundBot(f"{module}:{name}", name, doc[0] if doc else "", kind, is_droid(name)))
    return found
