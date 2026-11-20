"""Driving Model, Vehicle and Tuner Mode on StarPilot 7's model manager, vehicle selection and settings rows."""
from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any

import pytest

from openpilot.selfdrive.ui.tandem.settings.model import Models, StarPilotModels
from openpilot.selfdrive.ui.tandem.settings.tuner import GAPS, Tuner, Tunable, OVERRIDE, DEFAULT, FROM_STYLE
from openpilot.selfdrive.ui.tandem.settings.vehicle import CarOption, Vehicle, WheelButton
from openpilot.selfdrive.ui.tandem.tests.test_speed_steering_port import Owner, page
from openpilot.starpilot.models.catalog import DEFAULT_SMALL


class FakeManager:
  def __init__(self) -> None:
    self.actions: list[tuple[str, dict]] = []
    self.parked = True
    self.models = [
      {"value": DEFAULT_SMALL, "label": "Default", "installed": True, "communityFavorite": False, "requiresGpu": False, "builtin": True},
      {"value": "fav", "label": "Favorite", "installed": True, "communityFavorite": True, "requiresGpu": False, "builtin": False},
      {"value": "big", "label": "Big", "installed": False, "communityFavorite": False, "requiresGpu": True, "builtin": False},
    ]
    self.current = "fav"
    self.job: dict = {}

  def snapshot(self) -> dict:
    return {"models": self.models, "currentModel": self.current, "gpuAvailable": False, "downloading": bool(self.job),
            "modelToDownload": self.job.get("model", ""), "downloadProgress": self.job.get("detail"),
            "capabilities": {"delete": self.parked}}

  def action(self, action: str, payload: dict) -> dict:
    from openpilot.starpilot.models.manager import ModelError
    if action != "active" and not self.parked:
      raise ModelError("Turn the vehicle off before changing driving models")
    self.actions.append((action, payload))
    if action == "active":
      self.current = payload["model"]
    return {}


def test_models_come_from_starpilots_manager_and_refusals_are_shown() -> None:
  manager, notices = FakeManager(), []
  source = StarPilotModels(manager, notices.append, clock=lambda: 0.0)
  models = Models(source)
  assert [m.key for m in models.tab(1)] == ["fav"] and models.current_name() == "Favorite"
  assert not models.use_recommended and [m.key for m in models.unused()] == []
  models.set_use_recommended(True)
  assert manager.actions[-1] == ("active", {"profile": "small", "model": DEFAULT_SMALL}) and models.use_recommended
  assert [m.key for m in models.unused()] == ["fav"]
  manager.parked = False
  source.download("big")
  assert notices == ["Turn the vehicle off before changing driving models"] and source.removal_blocked() == "Park to remove models"


def test_download_progress_reads_starpilots_job() -> None:
  manager = FakeManager()
  manager.job = {"model": "big", "detail": {"phase": "downloading", "received": 45, "total": 100}}
  source = StarPilotModels(manager, clock=lambda: 0.0)
  assert source.downloading_key() == "big" and source.progress() == "45%"
  assert Models(source).status(source.models()[2]) == "downloading"


@dataclass(frozen=True)
class Snapshot:
  raw: bytes | None
  platform: str | None


class FakeSelection:
  def __init__(self) -> None:
    self.saved = Snapshot(None, None)
    self.parked = True

  def snapshot(self) -> Snapshot:
    return self.saved

  def choices(self) -> tuple[Any, ...]:
    return (SimpleNamespace(platform="HONDA_CIVIC", make="Honda", label="Honda Civic 2016-18"),
            SimpleNamespace(platform="TOYOTA_RAV4H", make="Toyota", label="Toyota RAV4 Hybrid 2019-21"))

  def choose(self, expected_raw: bytes | None, platform: str | None) -> Any:
    ok = self.parked and expected_raw == self.saved.raw
    if ok:
      self.saved = Snapshot(f"{platform}".encode(), platform)
    return SimpleNamespace(committed=ok)


class FakeDoors:
  def __init__(self) -> None:
    self.values: dict[str, bool] = {}

  def available(self) -> bool:
    return True

  def get(self, key: str) -> bool:
    return self.values.get(key, False)

  def set(self, key: str, on: bool) -> bool:
    self.values[key] = on
    return True


@pytest.fixture
def owner() -> Owner:
  return Owner({
    "wheel": {"wheel:LKASButtonControl": "No Action", "wheel:DistanceButtonControl": "Change Personality"},
    "vehicle": {"SNGHack": "Off"},
    "lane": {"LaneCentering": "On", "LaneCenterOffset": "0.0"},
    "torque": {}, "tuning": {},
    "profiles": {"profile:global_acceleration": "Comfort", "profile:global_braking": "Comfort", "ForceStops": "Off",
                 "ForceStopDistanceOffset": "0.0"},
    "relaxed": {"RelaxedFollow": "1.6"}, "standard": {"StandardFollow": "1.45"}, "aggressive": {"AggressiveFollow": "1.25"},
    "traffic": {"TrafficFollow": "0.75"},
  })


def with_rows(owner: Owner, page_name: str, **changes: Any) -> None:
  for key, row in owner.pages[page_name].items():
    owner.pages[page_name][key] = replace(row, **changes.get(key, {}))


def test_the_car_is_detected_or_chosen_through_starpilots_selection(owner: Owner) -> None:
  selection = FakeSelection()
  vehicle = Vehicle(selection, owner.rows, FakeDoors(), lambda: "TOYOTA_RAV4H")
  assert vehicle.car() == "Toyota RAV4 Hybrid 2019-21" and not vehicle.manual and vehicle.make() == "Toyota"
  assert vehicle.makes() == ["Honda", "Toyota"]
  assert vehicle.choose(CarOption("HONDA_CIVIC", "Honda Civic 2016-18"))
  assert vehicle.manual and vehicle.car() == "Honda Civic 2016-18"
  vehicle.use_detection()
  assert not vehicle.manual


def test_wheel_buttons_are_starpilots_wheel_rows_and_car_options_ask_first(owner: Owner) -> None:
  owner.pages["wheel"] = {k: replace(r, choices=("No Action", "Change Personality", "Pause Steering")) for k, r in owner.pages["wheel"].items()}
  vehicle = Vehicle(FakeSelection(), owner.rows, FakeDoors(), lambda: "")
  lkas = WheelButton("LKAS press", "wheel:LKASButtonControl")
  assert [b.key for b in vehicle.buttons()] == ["wheel:LKASButtonControl", "wheel:DistanceButtonControl"]
  vehicle.set_action(lkas, "Pause Steering")
  assert vehicle.action_name(lkas) == "Pause Steering"
  vehicle.set_extra("SNGHack", "On")
  assert page(owner, "vehicle")["SNGHack"] == "On" and owner.requests[-1].confirmation


def test_tuner_marks_overrides_against_starpilots_defaults_and_resets_them(owner: Owner) -> None:
  for name in ("relaxed", "standard", "aggressive", "traffic", "lane", "profiles"):
    for key, row in owner.pages[name].items():
      number = row.value.replace(".", "", 1).isdigit()
      owner.pages[name][key] = replace(row, default_value=row.value, step=0.05 if number else 0.0,
                                       choices=row.choices if number else ("Off", "On"))
  tuner = Tuner(owner.rows)
  relaxed = GAPS[0][1]
  assert tuner.status(relaxed) == DEFAULT
  tuner.set_number(relaxed, 1.8)
  assert tuner.status(relaxed) == OVERRIDE and tuner.following_changes() == 1
  assert tuner.status(Tunable("profiles", "profile:global_acceleration")) == FROM_STYLE
  assert [t.key for t in tuner.steering()] == ["LaneCenterOffset"]
  tuner.reset_all()
  assert page(owner, "relaxed")["RelaxedFollow"] == "1.6" and tuner.following_changes() == 0


def test_tuner_leaves_starpilots_manual_steering_tune_on_its_own_screens(owner: Owner) -> None:
  owner.pages["tuning"] = {"torque:surface:ff_gain_left": Owner({"x": {"k": "0.0"}}).pages["x"]["k"]}
  owner.pages["tuning"]["torque:surface:ff_gain_left"] = replace(owner.pages["tuning"]["torque:surface:ff_gain_left"],
                                                                  key="torque:surface:ff_gain_left", step=0.01)
  owner.pages["torque"] = {"torque:friction:value": replace(owner.pages["tuning"]["torque:surface:ff_gain_left"], key="torque:friction:value")}
  assert [t.key for t in Tuner(owner.rows).steering()] == ["torque:friction:value"]


def test_model_names_drop_starpilots_emoji_markers() -> None:
  from openpilot.selfdrive.ui.tandem.settings.model import model_name
  assert model_name("Regret Driven Framework V4 👀📡") == "Regret Driven Framework V4"
  assert model_name("Pop Model V2 😢") == "Pop Model V2"
  assert model_name("Watermelon Indigo v11") == "Watermelon Indigo v11"
  assert model_name("👀") == "👀"   # never empty
  manager = FakeManager()
  manager.models[1]["label"] = "Green Watermelon v8 👀📡"
  assert StarPilotModels(manager, clock=lambda: 0.0).models()[1].name == "Green Watermelon v8"
