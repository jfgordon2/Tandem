"""The Software tab on StarPilot 7: release's tab and Home on one shared software watch, with revision binding."""
from __future__ import annotations

import sys
from types import ModuleType
from typing import Any
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem import screens
from openpilot.selfdrive.ui.tandem.settings.software import Software
from openpilot.selfdrive.ui.tandem.software import HomeSoftware, InstallPreference, InstallTarget, SoftwareState, SoftwareWatch, Stage, project
from openpilot.starpilot.ui.brand import DISPLAY_VERSION
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.widgets import Widget

OLD, NEW = "a" * 40, "b" * 40


def fixtures() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
  """Native software status, permissions and release notes for a parked device."""
  status = {
    "installed": {"version": "0.11.3", "displayVersion": "7.0", "branch": "development", "commit": OLD},   # as on the device
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


def _watch(status: dict[str, Any], operations: dict[str, Any], params: dict[str, Any], authorized: bool = True) -> tuple[SoftwareWatch, Mock]:
  owner = Mock()
  owner.snapshot.return_value = operations
  owner.status.snapshot.return_value = status
  watch = SoftwareWatch(lambda: owner, params.get, lambda: authorized, Mock(), clock=lambda: 0.0)
  watch.state = project(status, operations, params.get)
  return watch, owner


def test_automatic_updates_turn_downloads_and_installs_on_together() -> None:
  status, operations, params = fixtures()
  watch, owner = _watch(status, operations, params)
  try:
    assert watch.automatic is False                   # downloads on, installs off: not automatic
    assert watch.set_automatic(True)
    watch._pending.result(timeout=5)
    assert [call.args for call in owner.action.call_args_list] == [
      ("install-preferences", {"action": "install-preferences", "automaticInstalls": True, "restartSchedule": "0 0 * * *",
                               "restartTimezone": "America/Chicago", "expectedRevision": "a" * 32}),
    ]                                                 # downloads were already on
    watch.poll()                                      # the next frame collects the result, as on screen
    owner.action.reset_mock()
    watch.state = project(status, dict(operations, automaticInstalls=True), params.get)
    assert watch.automatic is True
    assert watch.set_automatic(False)
    watch._pending.result(timeout=5)
    assert [call.args[0] for call in owner.action.call_args_list] == ["preferences", "install-preferences"]
    assert owner.action.call_args_list[0].args[1] == {"action": "preferences", "automaticDownloads": False, "expectedAutomaticDownloads": True}
  finally:
    watch.close()


def test_automatic_updates_can_start_with_no_saved_schedule() -> None:
  """Before anyone saved install preferences, StarPilot reports its default schedule and no revision to expect."""
  status, operations, params = fixtures()
  operations.update(automaticDownloads=False, automaticInstalls=None, installPreferenceRevision=None, restartTimezone="UTC")
  watch, owner = _watch(status, operations, params)
  try:
    assert watch.state.installs == InstallPreference(False, "0 0 * * *", "UTC", None)
    assert watch.set_automatic(True)
    watch._pending.result(timeout=5)
    assert owner.action.call_args_list[1].args[1]["expectedRevision"] is None
  finally:
    watch.close()


def test_a_refused_first_change_stops_the_second() -> None:
  status, operations, params = fixtures()
  operations.update(automaticDownloads=False)
  watch, owner = _watch(status, operations, params)
  owner.action.side_effect = RuntimeError("Update preference changed; refresh before saving")
  try:
    assert watch.set_automatic(True)
    watch._pending.result(timeout=5)
    assert owner.action.call_count == 1
    watch.poll()
    assert watch.failed
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


def test_writes_are_blocked_when_the_tab_loses_authority() -> None:
  owner = Mock()
  watch = SoftwareWatch(lambda: owner, Mock(), lambda: False, Mock())
  try:
    watch.state = SoftwareState(can_configure=True, can_check=True, can_download=True, branch="development", downloads=True,
                                installs=InstallPreference(False, "0 0 * * *", "UTC", "a" * 32))
    assert not watch.check()
    assert not watch.download()
    assert not watch.set_automatic(False)
    assert watch._pending is None
  finally:
    watch.close()


@pytest.mark.parametrize("stage,state,action", [
  (Stage.CURRENT, "current", "Check now"), (Stage.CHECKING, "busy", "Working…"), (Stage.AVAILABLE, "available", "Download"),
  (Stage.READY, "ready", "Restart to install"), (Stage.CHECK_FAILED, "failed", "Try again"), (Stage.PARK, "waiting", "Check now"),
])
def test_release_tab_states_follow_starpilots_stages(stage: Stage, state: str, action: str) -> None:
  watch = SoftwareWatch(Mock, Mock(), lambda: True, Mock())
  try:
    watch.state = SoftwareState(stage=stage)
    model = Software(watch, lambda key: "0.11.3 / development / 1abbbc6 / Nov 16", Mock())
    assert model.state() == state and model.action_label() == action
    # StarPilot's version, not openpilot's base version, and the commit stays out of sight
    assert model.version_parts() == (DISPLAY_VERSION, "development · Nov 16")
    if state == "waiting":
      assert model.status_line() == "Software actions are available while parked" and not model.can_act()
  finally:
    watch.close()


def test_release_tab_acts_on_exactly_what_it_shows() -> None:
  target = InstallTarget("development", OLD, NEW)
  watch = SoftwareWatch(Mock, Mock(), lambda: True, Mock())
  watch.install, watch.download, watch.check = Mock(), Mock(), Mock()   # type: ignore[method-assign]
  try:
    model = Software(watch, lambda key: None, Mock())
    watch.state = SoftwareState(stage=Stage.READY, home=HomeSoftware(target=target))
    model.act()
    watch.install.assert_called_once_with(target)
    watch.state = SoftwareState(stage=Stage.AVAILABLE, can_download=True, branch="development")
    model.act()
    watch.download.assert_called_once()
    watch.state = SoftwareState(stage=Stage.CURRENT, can_check=True)
    model.act()
    watch.check.assert_called_once()
  finally:
    watch.close()


@pytest.mark.parametrize("key,value", [("TANDEM_SETTINGS", "0"), ("STARPILOT_UI", "upstream")])
def test_recovery_uses_openpilots_settings(monkeypatch: pytest.MonkeyPatch, key: str, value: str) -> None:
  class SettingsLayout(Widget):
    """A native-settings stand-in with the upstream widget contract."""
    def __init__(self, **kwargs: Any) -> None:
      super().__init__()
      self.kwargs = kwargs

    def _render(self, rect: rl.Rectangle) -> None:
      pass

  native = ModuleType("openpilot.selfdrive.ui.layouts.settings.settings")
  native.SettingsLayout = SettingsLayout  # type: ignore[attr-defined]
  monkeypatch.setitem(sys.modules, native.__name__, native)
  monkeypatch.setenv(key, value)
  opened = Mock()
  layout = screens.settings(opened, lambda: True)
  assert type(layout) is SettingsLayout and layout.kwargs["on_open_arabesque"] is opened


def test_home_shows_starpilots_version_not_openpilots() -> None:
  """StarPilot's status carries openpilot's base version too; its own screens show StarPilot's (starpilot/ui/brand.py)."""
  from openpilot.selfdrive.ui.tandem.software import project_software
  status, operations, _ = fixtures()
  status["installed"]["displayVersion"] = DISPLAY_VERSION   # as StarPilot's status sets it
  assert project_software(status, operations).installed == DISPLAY_VERSION
  del status["installed"]["displayVersion"]
  assert project_software(status, operations).installed == "0.11.3"   # an older status without it

