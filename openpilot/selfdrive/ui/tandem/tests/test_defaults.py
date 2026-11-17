"""Reset Settings (settings/defaults.py): every Essentials default, through StarPilot's settings rows and Tandem's preferences."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from openpilot.selfdrive.ui.tandem import prefs
from openpilot.selfdrive.ui.tandem.settings.defaults import apply_essentials
from openpilot.selfdrive.ui.tandem.tests.test_display_alerts_port import FakeRoad
from openpilot.selfdrive.ui.tandem.tests.test_speed_steering_port import Owner, page
from openpilot.selfdrive.ui.tandem.tools.render.scene_driving import example_owner


class BatchStore:
  def __init__(self) -> None:
    self.values: dict = {"LongitudinalPersonality": 0}
    self.batches = 0

  def get_bool(self, key: str) -> bool:
    return bool(self.values.get(key, False))

  def get_int(self, key: str) -> int:
    return int(self.values.get(key, 0))

  def write(self, values: dict) -> None:
    self.values.update(values)

  def batch(self) -> object:
    store = self

    class Batch:
      def __enter__(self) -> None:
        store.batches += 1

      def __exit__(self, *args: object) -> None:
        pass
    return Batch()


@pytest.fixture
def changed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Owner:
  """A driver's settings, far from the defaults."""
  monkeypatch.setattr(prefs, "prefs_dir", lambda: tmp_path)
  owner = example_owner()
  for name, key, value in (("slc", "SLCConfirmation", "Both"), ("lane_change", "lane_change:auto", "On"),
                           ("curve", "CurveSpeedController", "Off"), ("appearance", "HidePersonalityAlerts", "Off"),
                           ("appearance", "DeveloperSidebar", "On"), ("sounds", "EngageVolume", "85")):
    owner.pages[name][key] = replace(owner.pages[name][key], value=value)
  prefs.TUNER_MODE.set(True)
  prefs.COMPASS.set(False)
  return owner


def test_reset_brings_back_every_essentials_default(changed: Owner) -> None:
  store, road, done = BatchStore(), FakeRoad(), []
  apply_essentials(store, changed.rows, road, on_done=lambda: done.append(True))  # type: ignore[arg-type]
  assert store.values["LongitudinalPersonality"] == 1 and store.batches == 1 and done
  slc = page(changed, "slc")
  assert slc["SpeedLimitController"] == "On" and slc["SLCConfirmation"] == "Higher only" and slc["slc:offset:1"] == "3"
  assert page(changed, "lane_change")["lane_change:auto"] == "Off"
  assert page(changed, "curve")["CurveSpeedController"] == "On" and page(changed, "conditional")["conditional:mode"] == "Automatic"
  assert page(changed, "appearance")["HidePersonalityAlerts"] == "On" and page(changed, "appearance")["DeveloperSidebar"] == "Off"
  assert page(changed, "sounds")["EngageVolume"] == "Auto" and page(changed, "sounds")["GreenLightAlert"] == "On"
  assert road.style["pathMode"] == "color"
  assert not prefs.TUNER_MODE.get() and prefs.COMPASS.get()
  assert page(changed, "relaxed")["RelaxedFollow"] == "1.6"   # Tuner Mode's override goes back to StarPilot's default


def test_settings_starpilot_wont_change_now_are_left_as_they_are(changed: Owner) -> None:
  for key, row in changed.pages["sounds"].items():
    changed.pages["sounds"][key] = replace(row, available=False)   # driving: sounds change only while parked
  apply_essentials(BatchStore(), changed.rows, FakeRoad())  # type: ignore[arg-type]
  assert page(changed, "sounds")["EngageVolume"] == "85" and page(changed, "slc")["SLCConfirmation"] == "Higher only"
