"""Bindings for release's General settings through StarPilot 7's owners."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import time

from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.prefs import TEMPERATURE, celsius
from openpilot.starpilot.galaxy.localization_settings import LocalizationSettingsOwner
from openpilot.starpilot.ui.display_owner import DisplayOwner
from openpilot.starpilot.ui.display_preferences import AUTO, BRIGHTNESS as BRIGHTNESS_KEYS, MASTER, SCREEN_OFF
from openpilot.starpilot.ui.feature_settings_state import FeatureRow, FeatureSettingsRequest
from openpilot.starpilot.ui.presentation import Profile

BRIGHTNESS = [(N_("Dimmer"), 40, 30), (N_("Auto"), AUTO, AUTO), (N_("Brighter"), 100, 100)]


def _level(value: int) -> str:
  """Format a brightness value for the native display owner."""
  return "Auto" if value == AUTO else str(value)


_BRIGHTNESS_VALUES = [(_level(parked), _level(driving)) for _, parked, driving in BRIGHTNESS]


def _request(row: FeatureRow, value: str) -> FeatureSettingsRequest:
  """Bind the change to the saved choice and dependencies displayed in the UI."""
  return FeatureSettingsRequest(row.key, row.source, value, dependencies=row.dependencies)


class General:
  """Read saved choices through their owners and refresh after each action."""

  def __init__(self, localization: LocalizationSettingsOwner, display: DisplayOwner, authorized: Callable[[], bool],
               refresh_language: Callable[[], None]) -> None:
    self._localization = localization
    self._display = display
    self._authorized = authorized
    self._refresh_language = refresh_language
    self._local_rows: dict[str, FeatureRow] = {}
    self._display_rows: dict[str, FeatureRow] = {}
    self._next = 0.0

  def refresh(self) -> None:
    """Read once on entry and after changes, including rejected writes."""
    self._local_rows = {row.key: row for row in self._localization.snapshot().rows}
    self._display_rows = {row.key: row for row in self._display.snapshot(Profile.LARGE).rows}
    self._next = time.monotonic() + 1.0

  def poll(self) -> None:
    """Observe updates from native settings or Galaxy while this page is open."""
    if time.monotonic() >= self._next:
      self.refresh()

  @property
  def metric(self) -> int:
    """Return the release segment index for the saved display units."""
    return int(self._local_rows["IsMetric"].value == "On")

  def metric_available(self) -> bool:
    """Use the localization owner's admission for changing units."""
    return self._local_rows["IsMetric"].available

  def set_metric(self, index: int) -> None:
    """Change units without changing the saved physical speed-limit offsets."""
    row = self._local_rows["IsMetric"]
    if row.available:
      self._localization.apply(_request(row, "On" if index == 1 else "Off"))
      self.refresh()

  @property
  def temperature(self) -> int:
    """Follow Units until a forecast temperature unit is saved."""
    return int(celsius(bool(self.metric)))

  def temperature_available(self) -> bool:
    """Allow writes to Tandem's forecast preference in the local UI."""
    return self._authorized()

  def set_temperature(self, index: int) -> None:
    """Save °F or °C independently of the speed and distance units."""
    if self.temperature_available():
      TEMPERATURE.set("C" if index == 1 else "F")

  def language(self) -> FeatureRow:
    """Return the active native name, supported names and source for the sheet."""
    return self._local_rows["LanguageSetting"]

  def language_name(self) -> str:
    """Return the name of the selected language."""
    return self.language().value

  def set_language(self, row: FeatureRow, name: str) -> bool:
    """Apply the choice from the open sheet and reload the live catalogs."""
    accepted = self._localization.apply(_request(row, name))
    if accepted:
      self._refresh_language()
    self.refresh()
    return bool(accepted)

  @property
  def brightness(self) -> int:
    """Select a preset when both effective brightness values match."""
    if self._display_rows[MASTER].value != "On":
      return 1
    saved = tuple(self._display_rows[key].value for key in BRIGHTNESS_KEYS)
    return next((i for i, values in enumerate(_BRIGHTNESS_VALUES) if saved == values), -1)

  def brightness_available(self) -> bool:
    """Allow preset edits when parked with readable, valid brightness values."""
    master = self._display_rows[MASTER]
    return master.available and all(not self._display_rows[key].repair_value for key in BRIGHTNESS_KEYS)

  def set_brightness(self, index: int) -> None:
    """Apply the release preset to the native parked and driving choices."""
    if self.brightness_available():
      try:
        self._apply_brightness(index)
      finally:
        self.refresh()

  def _apply_brightness(self, index: int) -> None:
    """Use exact saved sources and undo successful writes if a later one fails."""
    _, parked, driving = BRIGHTNESS[index]
    master = self._display_rows[MASTER]
    enabling = master.value != "On"
    if enabling and not self._write_display(_request(master, "On")):
      return

    dependencies = ((MASTER, b"1" if enabling else master.source),)
    undo: list[FeatureSettingsRequest] = []
    for key, target in zip(BRIGHTNESS_KEYS, (parked, driving), strict=True):
      row = self._display_rows[key]
      request = replace(_request(row, _level(target)), dependencies=dependencies)
      if not self._write_display(request):
        for original in reversed(undo):
          self._write_display(original)
        if enabling:
          self._write_display(FeatureSettingsRequest(MASTER, b"1", "Off"))
        return
      undo.append(FeatureSettingsRequest(key, str(target).encode(), row.value, dependencies=dependencies))

  def _write_display(self, request: FeatureSettingsRequest) -> bool:
    """Treat native Params write failures like a rejected save."""
    try:
      return self._display.apply(request)
    except RuntimeError:
      return False

  @property
  def standby(self) -> bool:
    """Return whether StarPilot turns the screen off after driving inactivity."""
    return self._display_rows[SCREEN_OFF].value == "On"

  def standby_available(self) -> bool:
    """Use the independent screen-off owner's parked gate."""
    return self._display_rows[SCREEN_OFF].available

  def set_standby(self, on: bool) -> None:
    """Set the native switch independently of custom brightness."""
    row = self._display_rows[SCREEN_OFF]
    if row.available:
      self._write_display(_request(row, "On" if on else "Off"))
      self.refresh()
