# Robocode adapter

Lets Robocode bots (Java `.jar` files, e.g. from the RoboRumble) fight in
Terrabots unchanged. It provides the parts of Robocode's API that bots program
against (`robocode.Robot`, `AdvancedRobot`, `TeamRobot`, `RateControlRobot`,
the events, `Rules`, `util.Utils`, data files) and talks to the Terrabots
engine over the sandbox's JSON protocol. Every bot runs in its own locked-down
container ([docs/sandbox.md](../../docs/sandbox.md)).

Written from Robocode's public API documentation, not from Robocode's source.
MPL-2.0 licensed, like the rest of Terrabots. It contains no bots: a bot's jar is
mounted into its container when it plays. Using it is in
[docs/robocode-bots.md](../../docs/robocode-bots.md).

```
src/robocode/            the API bots compile against (and _Peer: turn hand-over, units, events)
src/terrabots/robocode/  Host: the program the container starts; Json: protocol messages
```

Build the image (Java 17 runtime plus this adapter):

```bash
docker build -t terrabots-sandbox-robocode -f docker/sandbox-robocode.Dockerfile adapters/robocode/
```
