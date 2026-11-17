"""The Stage 4 delete confirmation and offline tile owner use isolated map roots."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem.settings.storage import StoragePanel
from openpilot.selfdrive.ui.tandem.settings.storage_owner import StorageOwner, StorageSample
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.starpilot.navigation.offline_roads import read_json, write_json
from openpilot.starpilot.tandem.map_removal import legacy_map_paths, remove_legacy_maps
from openpilot.starpilot.tandem.tile_removal import consume_clear_tiles, REPLY, REQUEST
from openpilot.system.ui.widgets import DialogResult


def test_delete_maps_confirmation_uses_displayed_generation() -> None:
  """A newer map selection cannot change what an open confirmation covers."""
  owner = Mock(spec=StorageOwner)
  owner.sample = StorageSample({"Maps": 1000}, map_generation="a" * 64)
  owner.record.return_value = False
  window = SettingsWindow({Tab.DEVICE: lambda: StoragePanel(owner, window)}, initial=Tab.DEVICE)
  window.top.items[2]._control._click_callback()
  owner.sample = StorageSample({"Maps": 2000}, map_generation="b" * 64)
  window._overlay._on_result(DialogResult.CONFIRM)
  owner.delete_maps.assert_called_once_with("a" * 64)


def test_old_release_maps_respect_routing_leases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  """Both older formats are removed after their reader releases the graph."""
  monkeypatch.delenv("OPENPILOT_PREFIX", raising=False)
  road, bundles, downloads, staging = legacy_map_paths(tmp_path.resolve())
  bundle = bundles / "iowa"
  for folder in (road, bundle, downloads, staging):
    folder.mkdir(parents=True)
    (folder / "map.bin").touch()
  chosen = bundles.parent / "selection.json"
  chosen.write_text("saved regions")
  with (bundle / ".lease").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_SH)
    assert not remove_legacy_maps(lambda: True, tmp_path.resolve())
    assert road.is_dir() and bundle.is_dir() and downloads.is_dir()
  assert remove_legacy_maps(lambda: True, tmp_path.resolve())
  assert not any(path.exists() for path in (road, bundles, downloads, staging))
  assert chosen.read_text() == "saved regions"


def test_tile_owner_removes_both_tile_providers_when_idle(tmp_path: Path) -> None:
  """Keep saved areas and remove the entire tile footprint only while parked."""
  root = tmp_path.resolve() / "roads"
  google = tmp_path.resolve() / "google"

  @contextmanager
  def exclusive():
    """Stand in for the native area lock."""
    yield

  state = SimpleNamespace(root=root, _exclusive=exclusive)
  daemon = SimpleNamespace(state=state, store=SimpleNamespace(root=root), progress={})
  provider = SimpleNamespace(store=SimpleNamespace(root=google), want=google / "wanted.json")
  params = Mock()
  params.get.return_value = None
  env = SimpleNamespace(onroad=False, route=[])
  paths = [root / kind for kind in ("saved", "driven", "cache")] + [google / "tiles"]
  for folder in paths:
    folder.mkdir(parents=True)
    (folder / "tile").touch()
  provider.want.write_text("{}")
  areas = root / "areas" / "example.json"
  write_json(areas, {"name": "Selected area"})
  token = "0" * 32
  write_json(root / REQUEST, {"id": token, "expires": time.monotonic() + 10})
  assert consume_clear_tiles(daemon, provider, env, params, lambda: {"destination": "active"})
  assert all(path.is_dir() for path in paths)
  assert read_json(root / REPLY)["complete"] is False
  params.get.return_value = "queued destination"
  write_json(root / REQUEST, {"id": token, "expires": time.monotonic() + 10})
  assert consume_clear_tiles(daemon, provider, env, params, dict)
  assert all(path.is_dir() for path in paths) and provider.want.exists()
  assert read_json(root / REPLY)["complete"] is False
  params.get.return_value = None
  write_json(root / REQUEST, {"id": token, "expires": time.monotonic() + 10})
  assert consume_clear_tiles(daemon, provider, env, params, dict)
  assert all(not path.exists() for path in paths)
  assert read_json(areas) == {"name": "Selected area"} and not provider.want.exists()
  assert read_json(root / REPLY)["complete"] is True
