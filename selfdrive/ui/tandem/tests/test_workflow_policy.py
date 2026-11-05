"""Unknown or changed inherited workflows must be reviewed before a push."""
import hashlib
import json

import pytest

from openpilot.selfdrive.ui.tandem.tools import workflow_policy


def test_repository_workflows_match_the_reviewed_policy():
  assert workflow_policy.check() >= 5


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
