"""Display and Alerts on StarPilot 7: release's choices on StarPilot's Appearance and Sounds rows and its road style."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from openpilot.selfdrive.ui.tandem import prefs
from openpilot.selfdrive.ui.tandem.settings.alerts import AUTO, GROUPS, SAFETY_FLOOR, Alerts
from openpilot.selfdrive.ui.tandem.settings.bundles import LEAD_INSIGHTS
from openpilot.selfdrive.ui.tandem.settings.display import PATH_STYLES, Display
from openpilot.selfdrive.ui.tandem.tests.test_speed_steering_port import Owner, page


class FakeRoad:
  def __init__(self) -> None:
    self.style: dict[str, str] = {}
    self.parked = True

  def get(self) -> dict:
    return dict(self.style)

  def editable(self) -> bool:
    return self.parked

  def set(self, changes: dict[str, str]) -> bool:
    if self.parked:
      self.style.update(changes)
    return self.parked


@pytest.fixture
def owner() -> Owner:
  return Owner({
    "sounds": {**{key: "Auto" for group in GROUPS for key in group.keys},
               "GreenLightAlert": "Off", "LoudBlindspotAlert": "Off", "LoudBlindspotAlertWhenDisengaged": "Off"},
    "appearance": {"CameraView": "Auto", "DriverCamera": "Off", "HidePersonalityAlerts": "Off", "BlindSpotMetrics": "On",
                   "DeveloperSidebar": "Off", "HideLeadMarker": "Off", "LeadInfo": "Off", "ShowBrakeStatus": "Off"},
  })


@pytest.fixture(autouse=True)
def prefs_folder(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setattr(prefs, "prefs_dir", lambda: tmp_path)


def test_volume_presets_set_every_level_and_auto_is_starpilots_auto(owner: Owner) -> None:
  model = Alerts(owner.rows)
  assert model.preset == 0
  model.set_preset(3)   # Loud
  assert [model.level(g) for g in GROUPS] == [g.levels[2] for g in GROUPS] and model.preset == 3
  assert page(owner, "sounds")["WarningImmediateVolume"] == "100"
  model.set_preset(0)
  assert {page(owner, "sounds")[k] for g in GROUPS for k in g.keys} == {"Auto"}


def test_one_level_makes_the_rest_normal_and_safety_keeps_its_floor(owner: Owner) -> None:
  model = Alerts(owner.rows)
  safety = next(g for g in GROUPS if g.safety)
  model.set_level(safety, 5)
  assert model.level(safety) == SAFETY_FLOOR
  assert all(model.level(g) == g.levels[1] for g in GROUPS if g != safety)
  assert model.preset == -1


def test_sounds_wait_until_parked(owner: Owner) -> None:
  for key, row in owner.pages["sounds"].items():
    owner.pages["sounds"][key] = replace(row, available=False)
  model = Alerts(owner.rows)
  model.set_preset(2)
  assert not model.editable() and model.level(GROUPS[0]) == AUTO and not owner.requests


def test_the_blind_spot_chime_is_both_of_starpilots_settings(owner: Owner) -> None:
  model = Alerts(owner.rows)
  model.set_chime("LoudBlindspotAlert", True)
  assert page(owner, "sounds")["LoudBlindspotAlert"] == page(owner, "sounds")["LoudBlindspotAlertWhenDisengaged"] == "On"
  model.set_chime("WeatherChime", False)
  assert not model.chime("WeatherChime")


def test_path_styles_are_starpilots_path_modes(owner: Owner) -> None:
  road = FakeRoad()
  model = Display(owner.rows, road)  # type: ignore[arg-type]
  assert PATH_STYLES[model.path_style][0] == "Acceleration"   # StarPilot's default path is openpilot's own
  model.set_path_style(0)
  assert road.style == {"pathMode": "color", "path": "#5AAAF880"} and model.path_style == 0
  model.set_path_style(1)
  assert road.style["pathMode"] == "rainbow" and model.path_style == 1
  road.parked = False
  model.set_path_style(2)
  assert model.path_style == 1 and not model.path_editable()


def test_display_rows_and_tandems_own_preferences(owner: Owner) -> None:
  model = Display(owner.rows, FakeRoad())  # type: ignore[arg-type]
  model.set_camera_view(2)
  model.set_driving_style_banner(False)
  model.set_blind_spot(False)
  assert page(owner, "appearance")["CameraView"] == "Wide" and model.camera_view == 2
  assert page(owner, "appearance")["HidePersonalityAlerts"] == "On" and not model.driving_style_banner
  assert not model.blind_spot
  model.set_text_size(1)
  model.set_lead_tag(False)
  assert model.text_size == 1 and not model.lead_tag


def test_lead_insights_turns_on_the_indicator_before_its_details(owner: Owner) -> None:
  model = Display(owner.rows, FakeRoad())  # type: ignore[arg-type]
  get, set_on = model.bundle(LEAD_INSIGHTS)
  set_on(True)
  assert get() and [r.key for r in owner.requests] == ["HideLeadMarker", "LeadInfo", "ShowBrakeStatus"]
  assert page(owner, "appearance")["LeadInfo"] == "Distance"
  set_on(False)
  assert not get() and [r.key for r in owner.requests][3:] == ["ShowBrakeStatus", "LeadInfo", "HideLeadMarker"]
