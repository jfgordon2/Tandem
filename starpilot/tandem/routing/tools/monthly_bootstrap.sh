#!/usr/bin/env bash
# Off-device only. No upstream build scripts, Docker images or shared caches.
set -euo pipefail
task_root="$1"
mkdir -p "$task_root"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  python3-venv build-essential ca-certificates curl osmium-tool spatialite-bin \
  libsqlite3-mod-spatialite libseccomp2 zlib1g-dev liblzma-dev liblzo2-dev liblz4-dev libzstd-dev libattr1-dev
python3 -m venv "$task_root/venv"
"$task_root/venv/bin/python" -m pip install --no-cache-dir 'pip==25.3' 'Shapely==2.1.2' 'pytest==8.4.2' 'zstandard==0.25.0'

# Ubuntu 24.04's older mksquashfs lacks the streaming -tar interface we use.
curl --fail --location --retry 3 \
  https://github.com/plougher/squashfs-tools/releases/download/4.7.2/squashfs-tools-4.7.2.tar.gz \
  --output "$task_root/squashfs-tools.tar.gz"
printf '%s  %s\n' 4672b5c47d9418d3a5ae5b243defc6d9eae8275b9771022247c6a6082c815914 "$task_root/squashfs-tools.tar.gz" | sha256sum --check
mkdir -p "$task_root/squashfs" "$task_root/bin"
tar -xzf "$task_root/squashfs-tools.tar.gz" --strip-components=1 -C "$task_root/squashfs"
make -C "$task_root/squashfs/squashfs-tools" -j2 mksquashfs unsquashfs
cp "$task_root/squashfs/squashfs-tools/mksquashfs" "$task_root/squashfs/squashfs-tools/unsquashfs" "$task_root/bin/"
echo "$task_root/bin" >> "$GITHUB_PATH"
echo "TANDEM_ROUTING_DIR=$task_root/runtime" >> "$GITHUB_ENV"
