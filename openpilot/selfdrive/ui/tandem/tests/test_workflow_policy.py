"""Unknown or changed inherited workflows must be reviewed before a push (tools/workflow_policy.py)."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from openpilot.selfdrive.ui.tandem.tools import workflow_policy


def test_repository_workflows_match_the_reviewed_policy() -> None:
  assert workflow_policy.check() >= 14
  notes = json.loads(workflow_policy.LOCK.read_text())["files"]
  assert all(entry["review"] for entry in notes.values())


def test_the_routing_maps_workflow_pins_official_actions_and_names_real_files() -> None:
  """Tandem's own data build: each action pinned to a reviewed commit, and every repository path it runs or watches exists."""
  text = (workflow_policy.ROOT / ".github/workflows/tandem_routing_maps.yaml").read_text()
  uses = re.findall(r"^\s*- uses:\s+(\S+)", text, flags=re.MULTILINE)
  assert uses and all(re.fullmatch(r"actions/[a-z0-9-]+@[a-f0-9]{40}", item) for item in uses)
  paths = {p for p in re.findall(r"(openpilot/[\w./-]+\.(?:py|sh|json))", text) if "/tools/out/" not in p}   # out/: its output
  assert paths and all((workflow_policy.ROOT / path).is_file() for path in paths), sorted(paths)
  modules = set(re.findall(r"-m (openpilot\.starpilot\.tandem\.routing\.tools\.\w+)", text))
  assert modules and all((workflow_policy.ROOT / (m.replace(".", "/") + ".py")).is_file() for m in modules)


@pytest.mark.parametrize("name", ["stale.yaml", "jenkins-pr-trigger.yaml"])
def test_inherited_writers_stay_inert_in_tandem(name: str) -> None:
  """Every job of these is gated to StarPilot's repository; a merge that drops a gate also fails the hash check."""
  text = (workflow_policy.ROOT / ".github/workflows" / name).read_text()
  jobs = text.split("\njobs:\n", 1)[1]
  names = [line for line in jobs.splitlines() if line.startswith("  ") and not line.startswith("   ") and line.endswith(":")]
  assert names and jobs.count("github.repository == 'StarPilotHQ/StarPilot'") >= len(names)


@pytest.mark.parametrize("change", ["new", "edit", "delete", "symlink"])
def test_workflow_changes_require_review(tmp_path: Path, change: str) -> None:
  folder = tmp_path / ".github/workflows"
  folder.mkdir(parents=True)
  path = folder / "old.yaml"
  path.write_text("reviewed workflow")
  lock = tmp_path / "policy.json"
  lock.write_text(json.dumps({"files": {".github/workflows/old.yaml": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                                                       "review": "ok"}}}))
  assert workflow_policy.check(tmp_path, lock) == 1
  if change == "new":
    (folder / "surprise.yml").write_text("unreviewed publisher")
  elif change == "edit":
    path.write_text("changed publisher")
  elif change == "delete":
    path.unlink()
  else:
    copy = tmp_path / "elsewhere"
    copy.write_text(path.read_text())
    path.unlink()
    path.symlink_to(copy)
  with pytest.raises(RuntimeError):
    workflow_policy.check(tmp_path, lock)


def test_update_records_hashes_and_names_files_without_a_note(tmp_path: Path) -> None:
  folder = tmp_path / ".github/workflows"
  folder.mkdir(parents=True)
  (folder / "old.yaml").write_text("v2")
  (folder / "new.yaml").write_text("added")
  lock = tmp_path / "policy.json"
  lock.write_text(json.dumps({"files": {".github/workflows/old.yaml": {"sha256": "stale", "review": "reviewed"}}}))
  assert workflow_policy.update(tmp_path, lock) == [".github/workflows/new.yaml"]
  assert workflow_policy.check(tmp_path, lock) == 2
