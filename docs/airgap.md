# Offline tournaments (air-gapped)

For the competition, submitted bots run on a dedicated offline machine (e.g. a
Raspberry Pi), carried over on a USB drive:

1. **Laptop:** `python tools/airgap/pack.py --config <private airgap.toml> --usb /mnt/e`
   downloads the private submissions and packs engine, bots and runner onto the
   drive (config format in `pack.py`).
2. **Tournament machine:** plug in the drive (label `TERRABOTS`); it runs the
   tournament sandboxed, writes `results/` and switches off. Its system is
   read-only, so switching off resets it. One-time setup:
   `sudo tools/airgap/pi/setup-pi.sh` on a fresh Raspberry Pi OS Lite (64-bit).
3. **Laptop:** `python tools/airgap/unpack.py --usb /mnt/e` accepts only numbers
   for exactly the packed entrants, then writes the leaderboard for review.

Status: pack, runner and unpack are tested on a laptop (including tampered
results). The Raspberry Pi setup (`tools/airgap/pi/`) is not yet tested on real
hardware.
