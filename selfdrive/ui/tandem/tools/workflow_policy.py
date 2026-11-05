"""Require review when upstream merges add or change GitHub workflow code."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LOCK = Path(__file__).with_name("workflow-policy.json")


def check(root=ROOT, lock=LOCK):
  reviewed = json.loads(lock.read_text())["files"]
  folder = root / ".github/workflows"
  actual = {path.relative_to(root).as_posix(): path for path in folder.rglob("*") if path.suffix in (".yaml", ".yml")}
  errors = [f"Unreviewed workflow/action: {name}" for name in sorted(actual.keys() - reviewed.keys())]
  errors.extend(f"Reviewed workflow/action missing: {name}" for name in sorted(reviewed.keys() - actual.keys()))
  for name in sorted(actual.keys() & reviewed.keys()):
    path = actual[name]
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != reviewed[name]["sha256"]:
      errors.append(f"Workflow/action changed; review its triggers, permissions and commands: {name}")
  if errors:
    raise RuntimeError("\n".join(errors))
  return len(actual)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--root", type=Path, default=ROOT)
  args = parser.parse_args()
  print(f"{check(args.root)} reviewed workflow/action files match the policy")


if __name__ == "__main__":
  main()
