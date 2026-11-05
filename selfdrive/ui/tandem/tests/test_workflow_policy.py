"""Unknown or changed inherited workflows must be reviewed before a push."""
import hashlib
import json
import re

import pytest

from openpilot.selfdrive.ui.tandem.tools import workflow_policy


def test_repository_workflows_match_the_reviewed_policy():
  assert workflow_policy.check() >= 5


def test_active_workflows_pin_official_actions_to_reviewed_commits():
  for name in ("fleet_safety.yaml", "tandem_routing_maps.yaml"):
    text = (workflow_policy.ROOT / ".github/workflows" / name).read_text()
    uses = re.findall(r"^\s*- uses:\s+(\S+)", text, flags=re.MULTILINE)
    assert uses and all(re.fullmatch(r"actions/[a-z0-9-]+@[a-f0-9]{40}", item) for item in uses), name


@pytest.mark.parametrize("change", ["new", "edit", "delete", "symlink"])
def test_workflow_changes_require_review(tmp_path, change):
  folder = tmp_path / ".github/workflows"
  folder.mkdir(parents=True)
  path = folder / "old.yaml"
  path.write_text("reviewed workflow")
  lock = tmp_path / "policy.json"
  lock.write_text(json.dumps({"files": {".github/workflows/old.yaml": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}}))
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
  with pytest.raises(RuntimeError, match="[Ww]orkflow"):
    workflow_policy.check(tmp_path, lock)
