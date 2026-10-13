#!/usr/bin/env bash
# One-time setup of the offline tournament machine (see docs/airgap.md).
#
# On a fresh Raspberry Pi OS Lite (64-bit, Bookworm), with internet, as root,
# from a copy of the Terrabots repository:
#     sudo tools/airgap/pi/setup-pi.sh
#
# Installs Docker and Python, builds the sandbox image, installs the USB
# trigger, then locks the machine down: no network, no radios, and a read-only
# system in which every boot starts from exactly this state ("factory reset" by
# switching off and on). It reboots at the end; after that it never needs
# internet again, until docker/sandbox.Dockerfile changes.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root (sudo)"; exit 1; }
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
OPT=/opt/terrabots
BOOT=/boot/firmware

echo "== 1/4 software (needs internet)"
apt-get update
apt-get install -y docker.io python3-venv
mkdir -p "$OPT"
python3 -m venv "$OPT/venv"
"$OPT/venv/bin/pip" install --no-cache-dir "numpy==2.4.*"

echo "== 2/4 sandbox image"
SHA=$(sha256sum "$REPO/docker/sandbox.Dockerfile" | cut -d' ' -f1)
docker build --label "terrabots.dockerfile.sha256=$SHA" -t terrabots-sandbox \
    -f "$REPO/docker/sandbox.Dockerfile" "$REPO/docker/"
docker save -o "$OPT/sandbox-image.tar" terrabots-sandbox

echo "== 3/4 USB trigger"
install -m 755 "$REPO/tools/airgap/pi/trigger.sh" "$OPT/trigger.sh"
install -m 644 "$REPO/tools/airgap/pi/terrabots-tournament@.service" /etc/systemd/system/
install -m 644 "$REPO/tools/airgap/pi/99-terrabots.rules" /etc/udev/rules.d/
# Docker's data lives in RAM: loaded fresh from sandbox-image.tar for every tournament.
grep -q " /var/lib/docker " /etc/fstab || cat >> /etc/fstab <<'FSTAB'
tmpfs /var/lib/docker     tmpfs rw,mode=711,size=4G 0 0
tmpfs /var/lib/containerd tmpfs rw,mode=711,size=1G 0 0
FSTAB
for unit in docker containerd; do
    mkdir -p "/etc/systemd/system/$unit.service.d"
    printf '[Unit]\nRequiresMountsFor=/var/lib/docker /var/lib/containerd\n' \
        > "/etc/systemd/system/$unit.service.d/ram.conf"
done
# Docker can only enforce the sandbox's memory limit with the memory cgroup on.
grep -q "cgroup_memory=1" "$BOOT/cmdline.txt" || sed -i '1 s/$/ cgroup_enable=memory cgroup_memory=1/' "$BOOT/cmdline.txt"
systemctl daemon-reload

echo "== 4/4 lock down"
for s in NetworkManager NetworkManager-wait-online wpa_supplicant bluetooth hciuart avahi-daemon \
         ModemManager ssh systemd-timesyncd; do
    systemctl disable "$s" 2>/dev/null || true
done
grep -q "disable-wifi" "$BOOT/config.txt" || printf '\ndtoverlay=disable-wifi\ndtoverlay=disable-bt\n' >> "$BOOT/config.txt"
# Read-only system and boot partition: changes live in RAM and vanish at power-off.
raspi-config nonint enable_overlayfs
raspi-config nonint enable_bootro || true

echo
echo "Done. Unplug the network cable, then the machine reboots into its locked-down state."
echo "Tip: switch it off, put the SD card in your laptop and save an image of it: that's your factory image."
sleep 5
reboot
