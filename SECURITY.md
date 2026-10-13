# Security

## Bots are code

A Terrabots bot is ordinary Python that runs inside the simulator's process with
your user's permissions. Loading a bot, including listing bots in the setup
screen (which imports every file in `bots/`), runs its code. Only run bots you
trust, the same way you would treat any script you download.

Turn time limits and the five-errors switch-off keep a slow or crashing bot from
stalling a battle. With `bot_isolation = "process"` each bot also runs in its own
process and is killed if it stops answering. That is not a sandbox: a bot process
runs with your permissions, and its replies are unpickled, so use it for your own
bots only.

**For other people's bots, use the sandbox** ([docs/sandbox.md](docs/sandbox.md)):
each bot in its own Docker container, without network, without access to your
files or other bots, with resource limits, speaking checked JSON with the engine
and never imported on the host. The tournament and the setup screen use it for
every bot in `contrib/` and `submissions/`; on the command line,
`terrabots-battle --headless --sandbox`. Its limits (container escapes through
kernel or Docker bugs) are listed there.

## The viewer server

`terrabots-battle` and `terrabots-run` listen on `localhost:8765` by default. Any
page that can reach that port can start or stop battles, and a battle can load
any importable bot spec. Don't bind to a public interface (`--host 0.0.0.0`) on an
untrusted network.

## Reporting a vulnerability

Please report security issues privately via GitHub's
[security advisories](https://github.com/devbyandre/terrabots/security/advisories/new)
instead of a public issue.
