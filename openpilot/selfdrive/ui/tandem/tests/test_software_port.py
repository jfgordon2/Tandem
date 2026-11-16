"""Cover permissions, progress and revision binding in the ported Software panel."""
from __future__ import annotations

from dataclasses import replace
import sys
from types import ModuleType
from typing import Any
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem import screens
from openpilot.selfdrive.ui.tandem.home_software import HomeSoftware, InstallTarget
from openpilot.selfdrive.ui.tandem.settings.software import Page, SoftwarePanel
from openpilot.selfdrive.ui.tandem.settings.software_state import InstallPreference, SoftwareState, SoftwareWatch, Stage, project
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.widgets import Widget

OLD, NEW = "a" * 40, "b" * 40


def fixtures() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
  """Native software status, permissions and release notes for a parked device."""
  status = {
    "installed": {"version": "7.0.0", "branch": "development", "commit": OLD},
    "updater": {"state": "idle", "targetBranch": "development", "lastCheckedAt": "2026-11-16T18:00:00Z",
                "finalizedUpdateReady": False, "targetChangeFound": False, "failedCount": 0},
  }
  operations = {"updaterAvailable": True, "parked": True, "canCheck": True, "canConfigure": True,
                "canDownload": True, "selectedTarget": "development", "automaticDownloads": True,
                "automaticInstalls": False, "restartSchedule": "0 0 * * *", "restartTimezone": "America/Chicago",
                "installPreferenceRevision": "a" * 32}
  values = {"UpdaterCurrentReleaseNotes": b"<p>Installed</p>", "UpdaterNewReleaseNotes": b"<p>Prepared</p>",
            "UpdaterNewDescription": "7.0.1 / development / bbbbbbb / Nov 16"}
  return status, operations, values


def test_software_measures_progress_only_when_reported() -> None:
  status, operations, params = fixtures()
  assert project(status, operations, params.get).stage == Stage.CURRENT
  status["updater"].update(targetChangeFound=True)
  assert project(status, operations, params.get).can_download
  status["updater"].update(state="downloading...")
  progress = project(status, dict(operations, progress={"percent": 42}), params.get)
  assert progress.stage == Stage.DOWNLOADING and progress.percent == 42
  assert not progress.can_check and not progress.can_download
  assert project(status, operations, params.get).percent is None
  status["updater"].update(state="finalizing update...")
  assert project(status, dict(operations, progress={"percent": 100}), params.get).stage == Stage.PREPARING


def test_staged_notes_require_matching_branch_and_commit() -> None:
  status, operations, params = fixtures()
  status["updater"].update(finalizedUpdateReady=True)
  operations.update(canInstall=True, preparedCommit=NEW)
  state = project(status, operations, params.get)
  assert state.stage == Stage.READY and state.home.target == InstallTarget("development", OLD, NEW)
  assert state.home.notes == "Prepared"
  assert state.installed_notes == "Installed"
  operations["preparedCommit"] = "c" * 40
  mismatch = project(status, operations, params.get)
  assert mismatch.stage != Stage.READY and mismatch.home.target is None


def test_update_preferences_keep_their_separate_expected_values() -> None:
  status, operations, params = fixtures()
  owner = Mock()
  owner.snapshot.return_value = operations
  owner.status.snapshot.return_value = status
  watch = SoftwareWatch(lambda: owner, params.get, lambda: True, Mock(), clock=lambda: 0.0)
  watch.state = project(status, operations, params.get)
  try:
    assert watch.automatic_downloads(False)
    assert not watch.automatic_installs(True)
    assert watch._pending is not None
    watch._pending.result(timeout=5)
    watch.poll()
    assert watch.automatic_installs(True)
    assert watch._pending is not None
    watch._pending.result(timeout=5)
    assert [call.args for call in owner.action.call_args_list] == [
      ("preferences", {"action": "preferences", "automaticDownloads": False, "expectedAutomaticDownloads": True}),
      ("install-preferences", {"action": "install-preferences", "automaticInstalls": True, "restartSchedule": "0 0 * * *",
                               "restartTimezone": "America/Chicago", "expectedRevision": "a" * 32}),
    ]
  finally:
    watch.close()


def test_restart_carries_both_commit_ids() -> None:
  status, operations, params = fixtures()
  operations.update(canInstall=True, preparedCommit=NEW)
  status["updater"].update(finalizedUpdateReady=True)
  owner = Mock()
  owner.snapshot.return_value = operations
  owner.status.snapshot.return_value = status
  watch = SoftwareWatch(lambda: owner, params.get, lambda: True, Mock())
  watch.state = project(status, operations, params.get)
  try:
    assert watch.install(InstallTarget("development", OLD, NEW))
    assert watch._pending is not None
    watch._pending.result(timeout=5)
    assert owner.action.call_args.args == ("install", {"action": "install", "branch": "development",
                                                       "expectedCommit": OLD, "selectedCommit": NEW})
    assert owner.action.call_args.kwargs["authorized"]()
  finally:
    watch.close()


def test_restart_expires_and_options_are_lazy() -> None:
  target = InstallTarget("development", OLD, NEW)
  owner = Mock()
  watch = SoftwareWatch(lambda: owner, Mock(), lambda: True, Mock())
  watch.state = SoftwareState(stage=Stage.READY, home=HomeSoftware(target=target))
  native = Mock(spec=Widget)
  make_options = Mock(return_value=native)
  panel = SoftwarePanel(lambda _authorized: watch, make_options, lambda: True)
  panel.show_event()
  try:
    make_options.assert_not_called()
    panel._open_update_notes(target)
    assert panel._can_restart()
    watch.state = replace(watch.state, home=HomeSoftware(target=replace(target, prepared_commit="c" * 40)))
    assert not panel._can_restart()
    panel._restart_shown()
    owner.action.assert_not_called()
    panel._open_options()
    make_options.assert_called_once()
    native.show_event.assert_called_once()
    panel.hide_event()
    assert panel._page == Page.MAIN and panel._shown_target is None
    native.hide_event.assert_called_once()
  finally:
    watch.close()


def test_writes_are_blocked_when_panel_loses_authority() -> None:
  owner = Mock()
  watch = SoftwareWatch(lambda: owner, Mock(), lambda: False, Mock())
  try:
    watch.state = SoftwareState(can_configure=True, can_check=True, can_download=True, branch="development", downloads=True,
                                installs=InstallPreference(False, "0 0 * * *", "UTC", "a" * 32))
    assert not watch.check()
    assert not watch.download()
    assert not watch.automatic_downloads(False)
    assert not watch.automatic_installs(True)
    assert watch._pending is None
  finally:
    watch.close()


@pytest.mark.parametrize("key,value", [("TANDEM_SETTINGS", "0"), ("STARPILOT_UI", "upstream")])
def test_recovery_uses_original_software_widget(monkeypatch: pytest.MonkeyPatch, key: str, value: str) -> None:
  class SoftwareLayout(Widget):
    """A native-panel stand-in with the upstream widget contract."""
    def _render(self, rect: rl.Rectangle) -> None:
      pass

  native = ModuleType("openpilot.selfdrive.ui.layouts.settings.software")
  native.SoftwareLayout = SoftwareLayout
  monkeypatch.setitem(sys.modules, native.__name__, native)
  monkeypatch.setenv(key, value)
  assert type(screens.software()) is SoftwareLayout
