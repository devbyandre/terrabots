#!/usr/bin/env bash
# Runs when a drive labelled TERRABOTS is plugged in (udev -> systemd).
# The ACT LED blinks while the tournament runs; the machine switches itself off
# when it's done, which (read-only system) also resets it. Then unplug the drive.
set -uo pipefail
DEV="$1"
OPT=/opt/terrabots
MNT=/run/terrabots-usb
WORK=/tmp/terrabots-run
LED=$(ls -d /sys/class/leds/ACT /sys/class/leds/led0 2>/dev/null | head -1)
[ -n "$LED" ] && echo heartbeat > "$LED/trigger"

mkdir -p "$MNT"
mount -o rw,nosuid,nodev,noexec "$DEV" "$MNT" || { systemctl poweroff; exit 1; }
if [ -f "$MNT/terrabots/manifest.json" ]; then
    docker image inspect terrabots-sandbox >/dev/null 2>&1 || docker load -i "$OPT/sandbox-image.tar"
    mkdir -p "$WORK"
    cp "$MNT/terrabots/runner.py" "$WORK/runner.py"      # run from RAM, not from the drive
    "$OPT/venv/bin/python" "$WORK/runner.py" --usb "$MNT" --work "$WORK/t" --python "$OPT/venv/bin/python" \
        > "$WORK/runner.log" 2>&1
    mkdir -p "$MNT/terrabots/results" && cp "$WORK/runner.log" "$MNT/terrabots/results/runner.log"
fi
sync
umount "$MNT"
[ -n "$LED" ] && echo none > "$LED/trigger"
systemctl poweroff
