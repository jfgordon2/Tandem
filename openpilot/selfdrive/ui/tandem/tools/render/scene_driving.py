"""Render the Driving tab's pages on StarPilot 7's settings rows (test stand-ins), each under its release mock's name."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import tempfile
from dataclasses import replace
from typing import Any

from openpilot.selfdrive.ui.tandem import prefs
from openpilot.selfdrive.ui.tandem.settings.alerts import GROUPS
from openpilot.selfdrive.ui.tandem.places import StarPilotPlaces
from openpilot.selfdrive.ui.tandem.tests.fakes import FakeNavigationOwner
from openpilot.selfdrive.ui.tandem.settings.driving_tab import DrivingServices, driving_hub
from openpilot.selfdrive.ui.tandem.settings.model import StarPilotModels
from openpilot.selfdrive.ui.tandem.settings.vehicle import Vehicle
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.selfdrive.ui.tandem.tests.test_display_alerts_port import FakeRoad
from openpilot.selfdrive.ui.tandem.tests.test_driving_port import FakeDoors, FakeManager, FakeSelection
from openpilot.selfdrive.ui.tandem.tests.test_speed_steering_port import OFFSET_KEYS, Owner, Store
from openpilot.starpilot.ui.raylib import rl


class ExampleLive:
  def engaged(self) -> bool:
    return False

  def offroad(self) -> bool:
    return True


class ExampleDevice:
  def driver_camera(self) -> None:
    pass

  def is_offroad(self) -> bool:
    return True

  def can_reset_driver_monitoring(self) -> bool:
    return True

  def reset_driver_monitoring(self) -> None:
    pass


def example_owner() -> Owner:
  """A parked RAV4 Hybrid's rows, with StarPilot's choices and defaults."""
  owner = Owner({
    "slc": {"SpeedLimitController": "On", "ShowSpeedLimits": "On", "SLCOnEngage": "On", "SLCConfirmation": "Higher only",
            **dict.fromkeys(OFFSET_KEYS, "3")},
    "profiles": {"profile:global_acceleration": "StarPilot Default", "profile:global_braking": "StarPilot Default",
                 "DisengageOnAccelerator": "On", "ForceStops": "Off", "ForceStopDistanceOffset": "0", "FasterLeadTakeoff": "Off"},
    "lane_change": {"lane_change:enabled": "On", "lane_change:auto": "Off"},
    "conditional": {"conditional:mode": "Automatic"}, "curve": {"CurveSpeedController": "On"}, "aol": {"AlwaysOnLateral": "On"},
    "sentry": {"sentry:enabled": "Off", "sentry:sensitivity": "0.040"},
    "sounds": {**{key: "Auto" for group in GROUPS for key in group.keys}, "GreenLightAlert": "On", "LeadDepartingAlert": "On",
               "LoudBlindspotAlert": "Off", "LoudBlindspotAlertWhenDisengaged": "Off"},
    "appearance": {"CameraView": "Standard", "DriverCamera": "On", "HidePersonalityAlerts": "On", "BlindSpotMetrics": "On",
                   "DeveloperSidebar": "Off", "HideLeadMarker": "Off", "LeadInfo": "Off", "ShowBrakeStatus": "Off"},
    "wheel": {"wheel:DistanceButtonControl": "Change Personality", "wheel:LongDistanceButtonControl": "Toggle Experimental Mode",
              "wheel:LKASButtonControl": "No Action"},
    "vehicle": {"SNGHack": "Off", "ToyotaAutoHold": "On"},
    "lane": {"LaneCentering": "On", "LaneCenterOffset": "0.0", "LaneCenteringStrength": "100"},
    "torque": {"SteerFriction": "0.12", "SteerLatAccel": "2.3"}, "tuning": {},
    "relaxed": {"RelaxedFollow": "1.6"}, "standard": {"StandardFollow": "1.45"}, "aggressive": {"AggressiveFollow": "1.25"},
    "traffic": {"TrafficFollow": "0.75"},
  })
  labels = {"wheel:DistanceButtonControl": "Distance short press", "wheel:LongDistanceButtonControl": "Distance long press",
            "wheel:LKASButtonControl": "LKAS press", "SNGHack": "Stop-and-Go Hack", "ToyotaAutoHold": "Automatic Brake Hold",
            "LaneCenterOffset": "Lane offset", "LaneCenteringStrength": "Lane Centering Strength", "SteerFriction": "Friction",
            "SteerLatAccel": "Lateral acceleration", "ForceStops": "Enhanced Stops", "ForceStopDistanceOffset": "Stop Distance Adjustment",
            "FasterLeadTakeoff": "Faster Takeoffs", "profile:global_acceleration": "Selected Acceleration Profile",
            "profile:global_braking": "Selected Deceleration Profile"}
  units = {"LaneCenterOffset": "m", "LaneCenteringStrength": "%", "ForceStopDistanceOffset": "ft", "RelaxedFollow": "s",
           "StandardFollow": "s", "AggressiveFollow": "s", "TrafficFollow": "s"}
  for name, rows in owner.pages.items():
    for key, row in rows.items():
      number = row.value.replace(".", "", 1).isdigit() and name not in ("sentry", "sounds", "slc")
      choices = row.choices or (("Off", "On") if row.value in ("Off", "On") else ())
      if key.startswith("wheel:"):
        choices = ("No Action", "Change Personality", "Toggle Experimental Mode", "Pause Steering")
      if key.startswith("profile:global"):
        choices = ("StarPilot Default", "Normal", "Comfort", "Sport")
      rows[key] = replace(row, label=labels.get(key, key), choices=choices, default_value=row.value, unit=units.get(key, ""),
                          step=0.05 if number else row.step, minimum=0.0, maximum=3.0 if units.get(key) == "s" else 100.0)
  rows = owner.pages["relaxed"]
  rows["RelaxedFollow"] = replace(rows["RelaxedFollow"], value="1.8")   # one override, as the mock shows
  return owner


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Each Driving page, parked, with sample rows."""
  with tempfile.TemporaryDirectory() as root:
    prefs.prefs_dir = lambda: Path(root)   # type: ignore[assignment]
    owner = example_owner()
    vehicle = Vehicle(FakeSelection(), owner.rows, FakeDoors(), lambda: "TOYOTA_RAV4H")
    services = DrivingServices(Store(LongitudinalPersonality=1, IsLdwEnabled=True, AlwaysOnDM=True), ExampleLive(), owner.rows,  # type: ignore[arg-type]
                               FakeRoad(), lambda: StarPilotModels(FakeManager(), clock=lambda: 0.0), lambda: vehicle, ExampleDevice(),
                               lambda: True, storage=lambda: {"drives": 40.0, "models": 6.0, "maps": 12.0, "free": 42.0},
                               navigation=lambda: StarPilotPlaces(FakeNavigationOwner))
    window: SettingsWindow
    window = SettingsWindow({Tab.DRIVING: lambda: hub}, initial=Tab.DRIVING)
    hub = driving_hub(window, services)
    window.show_event()
    bounds = rl.Rectangle(0, 0, 2160, 1080)

    def shot(name: str) -> None:
      frame(lambda: window.render(bounds))
      frame(lambda: window.render(bounds))
      save(f"{out}/{name}.png")

    shot("hub")
    for page, mock in (("speed_steering", "driving"), ("display", "display"), ("alerts", "alerts"), ("model", "model"),
                       ("vehicle", "drivingvehicle"), ("assistance", "assistance"), ("tuner", "tuner")):
      hub.pages[page]()
      shot(mock)
      window.back()
    hub.pages["speed_steering"]()
    window.top.select(2)   # Navigation
    shot("stage5-drivingnav")
    from openpilot.selfdrive.ui.tandem.map_keys import map_key_sheet
    sheet = map_key_sheet(window.dismiss)
    window.present(sheet)
    sheet._shown_at = None   # fully open, without waiting for its slide
    shot("stage5-mapboxkey")
    window.dismiss()
    window.back()
    hub.pages["tuner"]()
    for index, mock in ((1, "tunergas"), (2, "tunerfollowing")):
      window.top.select(index)
      shot(mock)
