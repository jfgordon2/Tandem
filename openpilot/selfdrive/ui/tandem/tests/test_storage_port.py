"""Storage & Data uses the release controls with current recording and model gates."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem.settings.storage import StoragePanel
from openpilot.selfdrive.ui.tandem.settings.storage_owner import StorageOwner, StorageSample, _bytes, remove_models, unused_models
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.starpilot.tandem.uploads import allow_uploads
from openpilot.system.ui.widgets import DialogResult


def test_storage_counts_hardlinked_maps_once(tmp_path: Path) -> None:
  """Shared tiles count once and external symlink targets stay out of the usage bar."""
  folder = tmp_path / "maps"
  folder.mkdir()
  first = folder / "tile"
  first.write_bytes(b"abc")
  (folder / "another-name").hardlink_to(first)
  outside = tmp_path / "unrelated"
  outside.write_bytes(b"excluded")
  (folder / "symlink").symlink_to(outside)
  assert _bytes((folder,)) == 3.0


def models_snapshot(*, active: str = "current", randomizer: bool = False) -> dict:
  """Represent the fields of StarPilot's native inventory used by Storage & Data."""
  return {"randomizer": randomizer, "downloading": False, "activeSmallModel": active, "activeBigModel": "large",
          "currentModel": "runtime", "models": [
            {"value": value, "installed": value != "missing", "builtin": value == "bundled"}
            for value in ("unselected", "bundled", active, "large", "runtime", "missing")
          ]}


def test_model_cleanup_keeps_bundled_active_and_randomizer_models() -> None:
  """Downloaded inactive models can be selected only while they are truly unused."""
  assert unused_models(models_snapshot()) == ("unselected",)
  assert not unused_models(models_snapshot(randomizer=True))


def test_model_cleanup_rechecks_selection_before_deleting() -> None:
  """A model chosen after confirmation remains available for the next drive."""
  model = Mock()
  model.snapshot.return_value = models_snapshot(active="unselected")
  assert not remove_models(model, ("unselected",), lambda: True)
  model.action.assert_not_called()
  model.snapshot.return_value = models_snapshot()
  assert remove_models(model, ("unselected",), lambda: True)
  model.action.assert_called_once_with("delete", {"model": "unselected"})


def test_recording_uses_native_toggle_without_bypassing_lock() -> None:
  """Keep the cabin camera fleet lock and delegate actual changes to the native toggle."""
  params, change = Mock(), Mock()
  params.get_bool.side_effect = lambda key: key == "RecordFrontLock"
  owner = StorageOwner(params, change, lambda: True, lambda: True, lambda: False)
  owner.set_record("RecordFront", True)
  change.assert_not_called()
  owner.set_record("RecordAudio", True)
  change.assert_called_once_with("RecordAudio", True)


def test_storage_panel_confirms_exact_model_set() -> None:
  """The release Remove dialog applies only to the displayed set after confirmation."""
  owner = Mock(spec=StorageOwner)
  owner.sample = StorageSample({"Drives": 100}, ("one",))
  owner.record.return_value = False
  window = SettingsWindow({Tab.DEVICE: lambda: StoragePanel(owner, window)}, initial=Tab.DEVICE)
  panel = window.top
  assert [item._title for item in panel.items[1:4]] == ["Recorded Drives", "Offline Maps", "Unused Models"]
  assert not panel.items[2]._control.enabled
  assert panel.items[-1]._control.enabled
  remove = panel.items[3]._control
  remove._click_callback()
  window._overlay._on_result(DialogResult.CANCEL)
  owner.delete_models.assert_not_called()

  remove._click_callback()
  owner.sample = StorageSample({"Drives": 100.0}, ("one", "new"))
  window._overlay._on_result(DialogResult.CONFIRM)
  owner.delete_models.assert_called_once_with(("one",))


def test_upload_policy_matches_release_and_native_default(tandem_prefs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  """The manager reads the same preference that the release segments save."""
  monkeypatch.delenv("STARPILOT_UI", raising=False)
  monkeypatch.delenv("TANDEM_SETTINGS", raising=False)
  params = Mock()
  owner = StorageOwner(params, Mock(), lambda: True, lambda: True, lambda: False)
  assert owner.uploads == 2
  assert allow_uploads(True, params, None)
  owner.set_uploads(0)
  assert owner.uploads == 0
  assert not allow_uploads(False, params, None) and not allow_uploads(True, params, None)
  owner.set_uploads(1)
  assert owner.uploads == 1
  assert allow_uploads(False, params, None) and not allow_uploads(True, params, None)
  owner.set_uploads(2)
  assert owner.uploads == 2
  assert allow_uploads(False, params, None) and allow_uploads(True, params, None)
  (tandem_prefs / ".tandem_uploads").write_text("unknown")
  assert owner.uploads == -1 and not allow_uploads(False, params, None)
  monkeypatch.setenv("TANDEM_SETTINGS", "0")
  assert allow_uploads(True, params, None)
  monkeypatch.delenv("TANDEM_SETTINGS")
  monkeypatch.setenv("STARPILOT_UI", "upstream")
  assert allow_uploads(True, params, None)
