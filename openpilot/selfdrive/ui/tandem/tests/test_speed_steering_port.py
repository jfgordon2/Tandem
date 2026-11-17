"""Speed & Steering on StarPilot 7: release's choices, read from and sent to StarPilot's settings rows."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pytest

from openpilot.selfdrive.ui.tandem.settings.speed_steering import OFFSET_KEYS, Assistance, SpeedSteering
from openpilot.selfdrive.ui.tandem.settings.starpilot7 import FeatureRows

CONFIRMED_ONLY = {"lane_change:enabled", "lane_change:auto", "sentry:enabled", "sentry:sensitivity"}


@dataclass(frozen=True)
class Row:
  key: str
  value: str
  available: bool = True
  step: float = 0.0
  source: bytes | None = b"saved"
  related_source: bytes | None = None
  vehicle_fingerprint: str | None = None
  capability: tuple | None = None
  dependencies: tuple = ()
  display_unit: str = ""


@dataclass(frozen=True)
class State:
  rows: tuple[Row, ...]


class Owner:
  """Holds rows per page; applies a request only when it matches the row as shown, as StarPilot's owners do."""

  def __init__(self, pages: dict[str, dict[str, str]]):
    self.pages = {page: {key: Row(key, value, step=1.0 if key.startswith("slc:offset") else 0.0) for key, value in rows.items()}
                  for page, rows in pages.items()}
    self.requests: list[Any] = []

  def rows(self, page: str) -> FeatureRows:
    return FeatureRows(lambda: State(tuple(self.pages[page].values())), lambda request: self.apply(page, request))

  def apply(self, page: str, request: Any) -> bool:
    self.requests.append(request)
    row = self.pages[page].get(request.key)
    if row is None or row.source != request.expected or (request.key in CONFIRMED_ONLY and not request.confirmation):
      return False
    self.pages[page][request.key] = replace(row, value=request.value)
    return True


class Store:
  def __init__(self, **values: Any):
    self.values = dict(values)

  def get_bool(self, key: str) -> bool:
    return bool(self.values.get(key, False))

  def get_int(self, key: str) -> int:
    return int(self.values.get(key, 0))

  def write(self, values: dict) -> None:
    self.values.update(values)


@pytest.fixture
def owner() -> Owner:
  return Owner({
    "slc": {"SpeedLimitController": "Off", "ShowSpeedLimits": "On", "SLCOnEngage": "Off", "SLCConfirmation": "Off",
            **dict.fromkeys(OFFSET_KEYS, "0")},
    "profiles": {"profile:global_acceleration": "StarPilot Default", "profile:global_braking": "Comfort", "DisengageOnAccelerator": "On"},
    "lane_change": {"lane_change:enabled": "On", "lane_change:auto": "Off", "lane_change:speed": "20.0"},
    "conditional": {"conditional:mode": "Chill"},
    "curve": {"CurveSpeedController": "Off"},
    "aol": {"AlwaysOnLateral": "On"},
    "sentry": {"sentry:enabled": "Off", "sentry:sensitivity": "0.040"},
  })


def page(owner: Owner, name: str) -> dict[str, str]:
  return {key: row.value for key, row in owner.pages[name].items()}


def test_driving_style_sets_the_personality_and_starpilots_presets(owner: Owner) -> None:
  store = Store(LongitudinalPersonality=1)
  model = SpeedSteering(store, owner.rows)
  assert model.style == 1
  model.set_style(0)   # Relaxed
  assert store.values["LongitudinalPersonality"] == 2
  assert page(owner, "profiles")["profile:global_acceleration"] == "Comfort" and page(owner, "profiles")["profile:global_braking"] == "Comfort"
  model.set_style(2)   # Sport: StarPilot's Aggressive personality
  assert store.values["LongitudinalPersonality"] == 0 and page(owner, "profiles")["profile:global_acceleration"] == "Sport"
  assert model.style == 2


def test_speed_limits_off_show_match(owner: Owner) -> None:
  model = SpeedSteering(Store(), owner.rows)
  assert model.speed_limits == 1
  model.set_speed_limits(2)
  assert page(owner, "slc")["SpeedLimitController"] == "On" and page(owner, "slc")["SLCOnEngage"] == "On" and model.matching
  model.set_speed_limits(0)
  assert page(owner, "slc")["ShowSpeedLimits"] == "Off" and model.speed_limits == 0


def test_one_offset_for_every_speed_range(owner: Owner) -> None:
  model = SpeedSteering(Store(), owner.rows)
  model.set_offset(3)
  assert {page(owner, "slc")[key] for key in OFFSET_KEYS} == {"3"} and model.offset == 3


@pytest.mark.parametrize("higher,lower,choice", [(1, 0, "Higher only"), (0, 1, "Lower only"), (1, 1, "Both"), (0, 0, "Off")])
def test_higher_and_lower_limits_are_starpilots_one_confirmation_choice(owner: Owner, higher: int, lower: int, choice: str) -> None:
  model = SpeedSteering(Store(), owner.rows)
  model.set_higher_limits(higher)
  model.set_lower_limits(lower)
  assert page(owner, "slc")["SLCConfirmation"] == choice
  assert (model.higher_limits, model.lower_limits) == (higher, lower)


def test_lane_changes_wait_for_the_drivers_confirmation(owner: Owner) -> None:
  asked = []
  model = SpeedSteering(Store(), owner.rows, confirm=lambda title, message, label, action: asked.append(action))
  model.set_lane_changes(1)
  assert page(owner, "lane_change")["lane_change:auto"] == "Off"   # nothing until confirmed
  asked[0]()
  assert page(owner, "lane_change")["lane_change:auto"] == "On" and model.lane_changes == 1
  assert all(r.confirmation for r in owner.requests if r.key.startswith("lane_change:"))
  model.set_lane_changes(1)
  assert len(asked) == 1                                         # already Auto: nothing to ask


def test_smart_slowdowns_are_automatic_driving_mode_and_the_curve_controller(owner: Owner) -> None:
  model = SpeedSteering(Store(), owner.rows)
  assert not model.smart_slowdowns
  model.set_smart_slowdowns(True)
  assert page(owner, "conditional")["conditional:mode"] == "Automatic" and page(owner, "curve")["CurveSpeedController"] == "On"
  assert model.smart_slowdowns
  model.set_smart_slowdowns(False)
  assert page(owner, "conditional")["conditional:mode"] == "Chill" and page(owner, "curve")["CurveSpeedController"] == "Off"


def test_a_row_starpilot_wont_change_now_is_left_alone(owner: Owner) -> None:
  owner.pages["aol"]["AlwaysOnLateral"] = replace(owner.pages["aol"]["AlwaysOnLateral"], available=False)
  model = SpeedSteering(Store(), owner.rows)
  model.set_always_on_steering(False)
  assert model.always_on_steering and not owner.requests


def test_a_request_carries_the_row_as_shown(owner: Owner) -> None:
  rows = owner.rows("aol")
  rows.state()
  owner.pages["aol"]["AlwaysOnLateral"] = replace(owner.pages["aol"]["AlwaysOnLateral"], source=b"changed elsewhere")
  assert not rows.set_on("AlwaysOnLateral", False)             # StarPilot refuses: it changed since it was shown
  assert rows.set_on("AlwaysOnLateral", False)                 # read again, then it goes through


def test_assistance_reads_owned_and_plain_settings_and_sentry_is_an_explicit_action(owner: Owner) -> None:
  store = Store(IsLdwEnabled=True)
  model = Assistance(store, live=None, rows=owner.rows)  # type: ignore[arg-type]
  assert model.get("IsLdwEnabled") and model.get("DisengageOnAccelerator")
  model.setter("DisengageOnAccelerator")(False)
  assert page(owner, "profiles")["DisengageOnAccelerator"] == "Off" and "DisengageOnAccelerator" not in store.values
  model.set_sentry(True)
  model.set_sentry_sensitivity(2)
  assert page(owner, "sentry") == {"sentry:enabled": "On", "sentry:sensitivity": "0.020"} and model.sentry_sensitivity == 2
