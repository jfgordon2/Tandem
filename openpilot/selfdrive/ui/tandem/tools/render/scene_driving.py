"""Render the Driving tab's pages on StarPilot 7's settings rows (test stand-ins), each under its release mock's name."""
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
import tempfile
from dataclasses import replace
from typing import Any

from openpilot.selfdrive.ui.tandem import prefs, tokens as T
from openpilot.selfdrive.ui.tandem.settings.alerts import GROUPS, Alerts, sound_pack_sheet
from openpilot.selfdrive.ui.tandem.places import StarPilotPlaces
from openpilot.selfdrive.ui.tandem.tests.fakes import FakeNavigationOwner, sample_maps
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
               "LoudBlindspotAlert": "Off", "LoudBlindspotAlertWhenDisengaged": "Off", "SoundPack": "StarPilot Sounds"},
    "appearance": {"CameraView": "Standard", "DriverCamera": "On", "HidePersonalityAlerts": "On", "BlindSpotMetrics": "On",
                   "DeveloperSidebar": "Off", "HideLeadMarker": "Off", "LeadInfo": "Off", "ShowBrakeStatus": "Off"},
    "wheel": {"wheel:DistanceButtonControl": "Change Personality", "wheel:LongDistanceButtonControl": "Toggle Experimental Mode",
              "wheel:LKASButtonControl": "No Action"},
    "vehicle": {"SNGHack": "Off", "ToyotaAutoHold": "On"},
    "lane": {"LaneCentering": "On", "LaneCenteringPauseOnSignal": "On", "LaneCenterOffset": "0.0", "LaneCenteringE2EAuthority": "50",
             "LaneCenteringStrength": "100"},
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
  units = {"LaneCenterOffset": "m", "LaneCenteringStrength": "%", "LaneCenteringE2EAuthority": "%", "ForceStopDistanceOffset": "ft", "RelaxedFollow": "s",
           "StandardFollow": "s", "AggressiveFollow": "s", "TrafficFollow": "s"}
  for name, rows in owner.pages.items():
    for key, row in rows.items():
      number = row.value.replace(".", "", 1).isdigit() and name not in ("sentry", "sounds", "slc")
      choices = row.choices or (("Off", "On") if row.value in ("Off", "On") else ())
      if key.startswith("wheel:"):
        choices = ("No Action", "Change Personality", "Toggle Experimental Mode", "Pause Steering")
      if key.startswith("profile:global"):
        choices = ("StarPilot Default", "Normal", "Comfort", "Sport")
      if key == "SoundPack":
        choices = ("StarPilot Sounds", "Stock Sounds", "Classic openpilot (pre-C4)", "openpilot 2025")
      rows[key] = replace(row, label=labels.get(key, key), choices=choices, default_value=row.value, unit=units.get(key, ""),
                          step=0.05 if number else row.step, minimum=0.0, maximum=3.0 if units.get(key) == "s" else 100.0)
  rows = owner.pages["relaxed"]
  rows["RelaxedFollow"] = replace(rows["RelaxedFollow"], value="1.8")   # one override, as the mock shows
  return owner


def alerts_shots(window: SettingsWindow, owner: Any, shot: Callable[[str], None]) -> None:
  """Alerts with Sound Pack (design/alerts-soundpack.html), and its picker sheet (soundpack.html), fully open."""
  shot("alerts-soundpack")
  sheet = sound_pack_sheet(Alerts(owner.rows), window)
  window.present(sheet)
  sheet._shown_at = None
  shot("soundpack")
  window.dismiss()


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Each Driving page, parked, with sample rows."""
  with tempfile.TemporaryDirectory() as root:
    prefs.prefs_dir = lambda: Path(root)   # type: ignore[assignment]
    owner = example_owner()
    vehicle = Vehicle(FakeSelection(), owner.rows, FakeDoors(), lambda: "TOYOTA_RAV4H")
    services = DrivingServices(Store(LongitudinalPersonality=1, IsLdwEnabled=True, AlwaysOnDM=True), ExampleLive(), owner.rows,  # type: ignore[arg-type]
                               FakeRoad(), lambda: StarPilotModels(FakeManager(), clock=lambda: 0.0), lambda: vehicle, ExampleDevice(),
                               lambda: True, storage=lambda: {"drives": 40.0, "models": 6.0, "maps": 12.0, "free": 42.0},
                               navigation=lambda: StarPilotPlaces(FakeNavigationOwner), maps=sample_maps)
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
      if page == "alerts":
        alerts_shots(window, owner, shot)
      if page == "tuner":
        shot("tuner-lanecentering")   # Steering, with the Lane Centering switch first
      window.back()
    theme_shots(window, hub, shot)
    os.environ["TANDEM_ROUTING"] = "1"
    os.environ["TANDEM_PREFS_DIR"] = str(Path(root) / "prefs")   # the routing policy, not this machine's
    from openpilot.starpilot.tandem.routing import config as C
    C.set_policy(offline_only=False, preferred="online")
    hub.pages["speed_steering"]()
    window.top.select(2)   # Navigation
    shot("stage5-drivingnav")
    from openpilot.selfdrive.ui.tandem.map_keys import map_key_sheet
    sheet = map_key_sheet(window.dismiss)
    window.present(sheet)
    sheet._shown_at = None   # fully open, without waiting for its slide
    shot("stage5-mapboxkey")
    window.dismiss()
    navigation = window.top._pages[2]
    navigation._scroll.set_offset(-T.px(57) * 3)   # the end of the list
    shot("stage5-drivingnav-end")
    navigation._scroll.set_offset(0)
    window.back()
    maps_shots(window, shot)
    hub.pages["tuner"]()
    for index, mock in ((1, "tunergas"), (2, "tunerfollowing")):
      window.top.select(index)
      shot(mock)


def theme_shots(window: SettingsWindow, hub: Any, shot: Callable[[str], None]) -> None:
  """Display › Theme (design/displaytheme.html) and its Turn Signal picker (signalpicker.html)."""
  from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
  from openpilot.selfdrive.ui.tandem.overlays import Sheet
  from openpilot.selfdrive.ui.tandem.settings.display import SignalPicker
  hub.pages["display"]()
  window.top.select(1)   # Theme
  shot("displaytheme")
  chosen = [0]
  sheet = Sheet("Turn Signal", SignalPicker(lambda: chosen[0], lambda i: chosen.__setitem__(0, i)),
                subtitle="Plays beside the speed while a blinker is on",
                actions=[Button("Done", window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss)
  window.present(sheet)
  sheet._shown_at = None   # fully open, without waiting for its slide
  shot("signalpicker")
  window.dismiss()
  window.back()


def maps_shots(window: SettingsWindow, shot: Callable[[str], None]) -> None:
  """Offline Maps, the region picker and a download's steps, each under its approved mock's name."""
  from openpilot.selfdrive.ui.tandem.settings.maps import Maps, MapsPage, RegionsPage
  sizes = lambda: {"Drives": 40e9, "Maps": 12e9, "Models": 6e9, "Free": 42e9, "Total": 100e9}  # noqa: E731
  window.push(MapsPage(Maps(sample_maps(), schedule=(lambda: "weekly", lambda choice: None)), lambda: None, sizes, window))
  shot("valhalla2-maps-home")
  window.back()
  regions = RegionsPage(Maps(sample_maps(road_ready=frozenset({IA, IL}), route_ready=frozenset({IA, IL}))), lambda: None)
  regions._select(1)
  window.push(regions)
  shot("valhalla3-regions-update")
  window.back()
  both = f"{IA},{IL}"
  for mock, job in (
      ("valhalla5-paired-iowa", {"id": "j", "selection": both, "phase": "road", "current_regions": [IA], "done": 1, "total": 4}),
      ("valhalla4-shared-download", {"id": "j", "selection": both, "phase": "download", "current_regions": [IA, IL],
                                     "done": 145 << 20, "total": 345 << 20}),
      ("valhalla4-shared-install", {"id": "j", "selection": both, "phase": "install", "stage": "build", "current_regions": [IA, IL],
                                    "done": 38, "total": 100}),
      ("valhalla4-shared-ready", {"id": "j", "selection": both, "phase": "ready", "regions_ready": [IA, IL]})):
    window.push(MapsPage(Maps(sample_maps(road_ready=frozenset({IA, IL}) if job["phase"] != "road" else frozenset(),
                                          route_ready=frozenset({IA, IL}) if job["phase"] == "ready" else frozenset(),
                                          chosen=frozenset({IA, IL}), job=job)), lambda: None, sizes, window))
    window.top._download._dismissed = False   # as it shows when the download finishes on screen
    shot(mock)
    window.back()


IA, IL = "us_state.IA", "us_state.IL"
