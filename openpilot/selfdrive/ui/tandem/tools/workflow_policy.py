"""Require review when upstream merges add or change GitHub workflow code.

Each workflow and composite action under .github/workflows is listed in workflow-policy.json with its SHA-256 and what it
does in Tandem's repository. A new, changed or missing file fails check() (and tests/test_workflow_policy.py) until its
triggers, permissions and commands are reviewed and the lock is updated with `--update`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
LOCK = Path(__file__).with_name("workflow-policy.json")


def _actual(root: Path) -> dict[str, Path]:
  folder = root / ".github/workflows"
  return {path.relative_to(root).as_posix(): path for path in folder.rglob("*") if path.suffix in (".yaml", ".yml")}


def check(root: Path = ROOT, lock: Path = LOCK) -> int:
  """Checks every workflow file against the lock.

  Args:
    root: The repository root.
    lock: The reviewed-files lock.

  Returns:
    How many workflow files matched.

  Raises:
    RuntimeError: Listing each unreviewed, changed or missing file.
  """
  reviewed = json.loads(lock.read_text())["files"]
  actual = _actual(root)
  errors = [f"Unreviewed workflow/action: {name}" for name in sorted(actual.keys() - reviewed.keys())]
  errors.extend(f"Reviewed workflow/action missing: {name}" for name in sorted(reviewed.keys() - actual.keys()))
  for name in sorted(actual.keys() & reviewed.keys()):
    path = actual[name]
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != reviewed[name]["sha256"]:
      errors.append(f"Workflow/action changed; review its triggers, permissions and commands: {name}")
  if errors:
    raise RuntimeError("\n".join(errors))
  return len(actual)


def update(root: Path = ROOT, lock: Path = LOCK) -> list[str]:
  """Records the current hashes after a review, keeping each file's note; returns the files that still need one."""
  policy = json.loads(lock.read_text())
  files = {}
  for name, path in sorted(_actual(root).items()):
    note = policy["files"].get(name, {}).get("review", "")
    files[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "review": note}
  policy["files"] = files
  lock.write_text(json.dumps(policy, indent=2) + "\n")
  return [name for name, entry in files.items() if not entry["review"]]


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--root", type=Path, default=ROOT)
  parser.add_argument("--update", action="store_true", help="record the reviewed files' hashes")
  args = parser.parse_args()
  if args.update:
    missing = update(args.root)
    print("Updated; add a review note for: " + ", ".join(missing) if missing else "Updated")
  else:
    print(f"{check(args.root)} reviewed workflow/action files match the policy")


if __name__ == "__main__":
  main()
