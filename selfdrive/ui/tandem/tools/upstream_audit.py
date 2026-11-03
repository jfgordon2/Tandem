#!/usr/bin/env python3
"""List the working tree's upstream edits. --check rejects external paths absent from the integration inventory."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OWNED = ("selfdrive/ui/tandem/", "starpilot/tandem/", "selfdrive/assets/fonts/Figtree",
         "selfdrive/assets/fonts/JetBrainsMono", "selfdrive/assets/fonts/NotoSans")


def owned(path: str) -> bool:
  return path.startswith(OWNED) or path in ("AGENTS.md", "RELEASES.md")


def git(*args: str) -> str:
  return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def audit(upstream: str) -> dict:
  statuses = {}
  for line in git("diff", "--no-renames", "--name-status", upstream).splitlines():
    status, path = line.split("\t", 1)
    statuses[path] = status
  rows = []
  for line in git("diff", "--no-renames", "--numstat", upstream).splitlines():
    added, removed, path = line.split("\t", 2)
    if not owned(path):
      rows.append({"path": path, "status": statuses[path], "added": int(added) if added != "-" else None,
                   "removed": int(removed) if removed != "-" else None})
  for path in git("ls-files", "--others", "--exclude-standard").splitlines():
    if not owned(path):
      rows.append({"path": path, "status": "?", "added": None, "removed": None})
  readme = (ROOT / "selfdrive/ui/tandem/README.md").read_text()
  return {"upstream": git("rev-parse", upstream), "head": git("rev-parse", "HEAD"),
          "external_files": sorted(rows, key=lambda row: row["path"]),
          "undocumented": [row["path"] for row in rows if f'`{row["path"]}`' not in readme]}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--upstream", default="upstream/StarPilot", help="upstream revision to compare directly with the working tree")
  parser.add_argument("--check", action="store_true", help="fail for undocumented edits outside owned paths")
  parser.add_argument("--json", action="store_true", help="emit the inventory as JSON")
  args = parser.parse_args()
  result = audit(args.upstream)
  if args.json:
    print(json.dumps(result, indent=2))
  else:
    rows = result["external_files"]
    added, removed = (sum(row[key] or 0 for row in rows) for key in ("added", "removed"))
    print(f"{len(rows)} external paths, +{added}/-{removed} text lines vs {result['upstream'][:10]}")
    for row in rows:
      print(f"{row['status']} {row['path']} (+{row['added']}, -{row['removed']})")
    if result["undocumented"]:
      print("Missing from README integration inventory: " + ", ".join(result["undocumented"]))
  return 1 if args.check and result["undocumented"] else 0


if __name__ == "__main__":
  raise SystemExit(main())
