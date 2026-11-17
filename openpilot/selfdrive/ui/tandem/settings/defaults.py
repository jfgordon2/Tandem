"""The Essentials defaults: what Reset Settings and first-run setup restore. Each line uses the same control a driver would.

On StarPilot 7 the driving settings go through StarPilot's owners (settings/starpilot7.py), which change sounds, the
display and the path only while parked; a value StarPilot won't change now is left as it is. Vehicle choices (the car,
buttons, door locks) and device choices (units, Wi-Fi, pairing) are left alone. Release's boot logo, compass param,
Speed Limit Change chime and holiday themes have no StarPilot 7 setting.
"""
from __future__ import annotations

from collections.abc import Callable

from openpilot.selfdrive.ui.tandem.prefs import TUNER_MODE
from openpilot.selfdrive.ui.tandem.settings.alerts import Alerts
from openpilot.selfdrive.ui.tandem.settings.bundles import BUNDLES
from openpilot.selfdrive.ui.tandem.settings.display import Display
from openpilot.selfdrive.ui.tandem.settings.speed_steering import Confirm, Rows, SpeedSteering, Weather
from openpilot.selfdrive.ui.tandem.settings.starpilot7 import RoadStyle
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner

SPEED_LIMIT_OFFSET = 3
CHIMES = (("GreenLightAlert", True), ("LeadDepartingAlert", True), ("LoudBlindspotAlert", False), ("WeatherChime", True))


def apply_essentials(store: SettingsStore, rows: Rows, road: RoadStyle, confirm: Confirm = lambda title, message, label, action: action(),
                     on_done: Callable[[], None] = lambda: None) -> None:
  """Apply every Essentials default.

  Args:
    store: Plain openpilot settings.
    rows: StarPilot's settings pages.
    road: The path's look.
    confirm: Asks before a change StarPilot makes only on confirmation (lane changes going to Auto); the default
      answers yes, for a caller that already asked (Reset Settings).
    on_done: Runs after the writes.
  """
  with store.batch():
    speed = SpeedSteering(store, rows, confirm)
    speed.set_style(1)                      # Standard
    speed.set_speed_limits(2)               # Match
    speed.set_offset(SPEED_LIMIT_OFFSET)
    speed.set_higher_limits(1)              # Tap to confirm
    speed.set_lower_limits(0)               # Update automatically
    speed.set_max_follows(True)
    speed.set_lane_changes(0)               # Nudge
    speed.set_smart_slowdowns(True)
    speed.set_always_on_steering(True)
    Weather().set_heads_up(True)

    display = Display(rows, road)
    display.set_path_style(0)               # Standard
    display.set_driving_style_banner(False)
    display.set_compass(True)
    display.set_blind_spot(True)
    display.set_camera_view(1)              # Standard

    alerts = Alerts(rows)
    alerts.set_preset(0)                    # Auto
    for key, on in CHIMES:
      alerts.set_chime(key, on)

    for bundle in BUNDLES:
      bundle.set(rows, False)
    Tuner(rows).reset_all()
    TUNER_MODE.set(False)
  on_done()
