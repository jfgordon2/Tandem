"""The Essentials defaults: what Reset Settings restores. Each line uses the same control a driver would."""
from __future__ import annotations
from collections.abc import Callable
from typing import TYPE_CHECKING

from openpilot.selfdrive.ui.tandem.settings.alerts import Alerts
from openpilot.selfdrive.ui.tandem.settings.bundles import BUNDLES
from openpilot.selfdrive.ui.tandem.settings.display import TANDEM_LOGO, Display
from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering, Weather
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.display import BootLogoSource

SPEED_LIMIT_OFFSET = 3


def apply_essentials(store: SettingsStore, boot_logos: Callable[[], BootLogoSource] | None = None) -> None:
  """Vehicle choices (profile, car, buttons) and device choices (units, Wi-Fi, pairing) are left alone.

  boot_logos makes the boot logo source that installs Tandem's logo; without it only the param is set.
  """
  with store.batch():
    _apply(store, boot_logos)


def _apply(store: SettingsStore, boot_logos: Callable[[], BootLogoSource] | None = None) -> None:
  speed = SpeedSteering(store)
  speed.set_style(1)                      # Standard
  speed.set_speed_limits(2)               # Match
  speed.set_offset(SPEED_LIMIT_OFFSET)
  speed.set_higher_limits(1)              # Tap to confirm
  speed.set_lower_limits(0)               # Update automatically
  speed.set_max_follows(True)
  store.write({"SLCMapboxFiller": True})   # Mapbox fills in limits the maps don't have (with a key)
  speed.set_lane_changes(0)               # Nudge
  speed.set_smart_slowdowns(True)
  speed.set_always_on_steering(True)
  Weather(store).set_mode(0)              # Auto

  display = Display(store, boot_logos)
  display.set_path_style(0)               # Standard
  display.set_driving_style_banner(False)
  display.set_compass(True)
  display.set_blind_spot(True)
  display.set_camera_view(1)              # Standard
  display.set_boot_logo(TANDEM_LOGO)

  alerts = Alerts(store)
  alerts.set_preset(0)                    # Auto
  for key, on in (("GreenLightAlert", True), ("LeadDepartingAlert", True), ("SpeedLimitChangedAlert", False),
                  ("LoudBlindspotAlert", False), ("WeatherChime", True)):
    alerts.set_chime(key, on)

  for bundle in BUNDLES:
    bundle.set(store, False)
  Tuner(store).reset_all()
  store.write({"HolidayThemes": False})   # this redesign has no holiday themes
