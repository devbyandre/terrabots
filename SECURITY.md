# Security

## Bots are code

A Terrabots bot is ordinary Python that runs inside the simulator's process with
your user's permissions. Loading a bot, including listing bots in the setup
screen (which imports every file in `bots/`), runs its code. Only run bots you
trust, the same way you would treat any script you download.

Turn time limits and the five-errors switch-off keep a slow or crashing bot from
stalling a battle. They are not a sandbox. Running each bot in its own
subprocess is on the roadmap.

## The viewer server

`terrabots-battle` and `terrabots-run` listen on `localhost:8765` by default. Any
page that can reach that port can start or stop battles, and a battle can load
any importable bot spec. Don't bind to a public interface (`--host 0.0.0.0`) on an
untrusted network.

## Reporting a vulnerability

Please report security issues privately via GitHub's
[security advisories](https://github.com/devbyandre/terrabots/security/advisories/new)
instead of a public issue.
