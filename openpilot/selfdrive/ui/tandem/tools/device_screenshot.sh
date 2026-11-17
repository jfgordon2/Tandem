#!/usr/bin/env bash
# Save what the comma's screen shows to a PNG on this computer (screenshot.py on the device does the capture).
#   tools/device_screenshot.sh <device address> [output.png]
# A sleeping screen wakes as a touch would; the picture comes about a second later. Needs SSH access to comma@<address>;
# SSH_OPTS adds ssh options (e.g. SSH_OPTS="-o HostKeyAlias=<saved address>" after the device's address changes).
set -euo pipefail
host="${1:?usage: device_screenshot.sh <device address> [output.png]}"
out="${2:-tandem-screenshot.png}"
ssh -o ConnectTimeout=8 ${SSH_OPTS:-} "comma@$host" 'rm -f /tmp/tandem-screenshot.png; touch /tmp/tandem-screenshot
for _ in $(seq 1 60); do [ -f /tmp/tandem-screenshot.png ] && exit 0; sleep 0.25; done
echo "No screenshot: is the UI running with Tandem screens on?" >&2; exit 1'
scp -q -o ConnectTimeout=8 ${SSH_OPTS:-} "comma@$host:/tmp/tandem-screenshot.png" "$out"
echo "$out"
