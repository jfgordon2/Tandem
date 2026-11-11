import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from openpilot.starpilot.tandem import dashboard_worker


def test_inherited_dashboard_lock_excludes_another_launcher_until_worker_exits(tmp_path: Path) -> None:
  status_path = tmp_path / "analyzer.json"
  with dashboard_worker.launch_lock(status_path) as lock_fd:
    assert lock_fd is not None
    worker = subprocess.Popen(
      [sys.executable, "-c", "import sys; sys.stdin.read()"],
      stdin=subprocess.PIPE, pass_fds=(lock_fd,),
    )

  contender = """
import sys
from pathlib import Path
from openpilot.starpilot.tandem.dashboard_worker import launch_lock

with launch_lock(Path(sys.argv[1])) as fd:
  sys.exit(0 if fd is None else 1)
"""
  try:
    result = subprocess.run([sys.executable, "-c", contender, str(status_path)], timeout=5, check=False)
    assert result.returncode == 0
  finally:
    worker.kill()
    worker.communicate(timeout=5)

  result = subprocess.run([sys.executable, "-c", contender, str(status_path)], timeout=5, check=False)
  assert result.returncode == 1


def test_dashboard_worker_exits_before_loading_analyzer_when_onroad(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
  from openpilot.common import params

  class OnroadParams:
    def get_bool(self, key: str) -> bool:
      assert key == "IsOnroad"
      return True

  analyzer = ModuleType("openpilot.starpilot.system.the_galaxy.utilities")

  def fail(_paths: list[str]) -> None:
    pytest.fail("the dashboard worker started onroad")

  monkeypatch.setattr(analyzer, "warm_dashboard_stats", fail, raising=False)
  monkeypatch.setitem(sys.modules, analyzer.__name__, analyzer)
  monkeypatch.setattr(params, "Params", OnroadParams)

  with dashboard_worker.launch_lock(tmp_path / "analyzer.json") as lock_fd:
    assert lock_fd is not None
    os.set_inheritable(lock_fd, True)
    monkeypatch.setattr(sys, "argv", [dashboard_worker.MODULE, str(lock_fd), "[]"])
    dashboard_worker.main()
    assert not os.get_inheritable(lock_fd)
