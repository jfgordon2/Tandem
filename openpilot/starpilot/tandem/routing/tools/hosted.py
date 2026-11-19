"""Inspect and reclaim scratch space on a disposable GitHub-hosted Ubuntu VM."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

# Leave Python, Node, the runner and checkout alone. These SDKs are unrelated to
# an OSM build. Never accept a caller-supplied path for privileged deletion.
UNUSED_SDKS = ("/usr/local/lib/android", "/usr/share/dotnet", "/opt/ghc", "/usr/local/.ghcup",
               "/opt/hostedtoolcache/CodeQL", "/usr/local/share/powershell")


def prepare():
  if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
      or os.environ.get("RUNNER_OS") != "Linux"):
    raise RuntimeError("Scratch cleanup is only available on a disposable GitHub-hosted Linux runner")
  subprocess.run(["sudo", "rm", "-rf", "--", *UNUSED_SDKS], check=True)


def report(path):
  memory = {}
  if Path("/proc/meminfo").exists():
    memory = {key: int(value.split()[0]) * 1024 for key, value in
              (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines()) if key in ("MemTotal", "MemAvailable")}
  disk = shutil.disk_usage(path)
  return {"cpus": os.cpu_count(), "memory": memory, "disk": {"total": disk.total, "free": disk.free},
          "image": os.environ.get("ImageVersion", ""), "runner": os.environ.get("RUNNER_ENVIRONMENT", "")}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--prepare", action="store_true")
  parser.add_argument("--out", type=Path, required=True)
  args = parser.parse_args()
  args.out.parent.mkdir(parents=True, exist_ok=True)
  before = report(args.out.parent)
  if args.prepare:
    prepare()
  result = {"before": before, "after": report(args.out.parent)}
  args.out.write_text(json.dumps(result, indent=2) + "\n")
  print(json.dumps(result), flush=True)


if __name__ == "__main__":
  main()
