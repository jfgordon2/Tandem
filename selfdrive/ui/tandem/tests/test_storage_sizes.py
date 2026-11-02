"""Desktop storage polling works without the device's /data mount."""
import shutil
from pathlib import Path
from types import SimpleNamespace

from openpilot.selfdrive.ui.tandem.settings.device_sections import StorageSizes
from openpilot.system import hardware


def test_desktop_measures_the_home_filesystem_without_data(monkeypatch, tmp_path):
  monkeypatch.setattr(hardware, "PC", True)
  monkeypatch.setattr(Path, "home", lambda: tmp_path)
  disk_usage = shutil.disk_usage
  queried = []

  def desktop_disk_usage(path):
    assert path == tmp_path     # /data is not available on a developer's Mac
    queried.append(path)
    return disk_usage(path)

  monkeypatch.setattr(shutil, "disk_usage", desktop_disk_usage)
  sizes = StorageSizes()
  sizes._measuring = True
  sizes._measure(0)

  assert queried == [tmp_path]
  assert sizes.sizes()["Total"] > 0
  assert sizes.sizes()["Free"] >= 0
  assert not sizes._measuring
  sizes.sizes()
  assert queried == [tmp_path]  # a successful measurement is cached between frames


def test_device_still_measures_the_data_filesystem(monkeypatch):
  monkeypatch.setattr(hardware, "PC", False)
  queried = []

  def device_disk_usage(path):
    queried.append(path)
    return SimpleNamespace(total=1000, free=400)

  monkeypatch.setattr(shutil, "disk_usage", device_disk_usage)
  sizes = StorageSizes()
  sizes._measure(0)

  assert queried == ["/data"]
  assert sizes.sizes()["Total"] == 1000
  assert sizes.sizes()["Free"] == 400
