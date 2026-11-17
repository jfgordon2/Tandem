"""StarPilot 7's settings, for release's settings models.

StarPilot 7 keeps most driving settings behind its feature-settings owner: each page is a list of rows (key, value,
choices, whether it can change now), and a change is accepted only as a request bound to the row as it was shown.
FeatureRows reads a page and sends changes that way, so release's models (speed_steering.py and the rest) keep their
methods and their pages stay release's. Plain openpilot settings stay in store.py.

StarPilotOwners makes the owners with the permissions StarPilot 7's own settings screen uses (runtime_app.py): changes
only while settings are open, car-specific groups only with a matching car, and parked-only groups only when StarPilot
confirms the car is parked. Imported only on the device.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

REFRESH_S = 0.5   # a page is read at most this often; a change reads it again at once


class FeatureRows:
  """One of StarPilot 7's settings pages, read at most every REFRESH_S, with changes sent as requests for the rows shown.

  Args:
    read: Reads the page (an owner's snapshot), returning a FeatureSettingsState.
    apply: Sends one FeatureSettingsRequest to the owner; True when it saved.
    clock: Monotonic seconds.
  """

  def __init__(self, read: Callable[[], Any], apply: Callable[[Any], bool], clock: Callable[[], float] = time.monotonic):
    self._read, self._apply, self._clock = read, apply, clock
    self._state: Any = None
    self._read_at = -1e9

  def state(self) -> Any:
    """The page's FeatureSettingsState, read again when it's older than REFRESH_S."""
    now = self._clock()
    if self._state is None or now - self._read_at >= REFRESH_S:
      self._state = self._read()
      self._read_at = now
    return self._state

  def refresh(self) -> None:
    """Read the page again on next use."""
    self._state = None

  def row(self, key: str) -> Any | None:
    return next((r for r in self.state().rows if r.key == key), None)

  def value(self, key: str, default: str = "") -> str:
    row = self.row(key)
    return str(row.value) if row is not None else default

  def on(self, key: str) -> bool:
    return self.value(key) == "On"

  def number(self, key: str, default: float = 0.0) -> float:
    try:
      return float(self.value(key))
    except ValueError:
      return default

  def available(self, key: str) -> bool:
    """Whether StarPilot would accept a change to this row now (present, and allowed in the current car and state)."""
    row = self.row(key)
    return bool(row is not None and row.available)

  def set(self, key: str, value: str, confirmed: bool = False) -> bool:
    """Ask StarPilot to change a row to value, bound to the row as last read; True when it saved.

    Args:
      key: The row's key.
      value: The new value as StarPilot shows it ("On", a choice's label, or a number).
      confirmed: The driver confirmed this change in a dialog, for rows StarPilot changes only on confirmation.
    """
    from openpilot.starpilot.ui.feature_settings_state import row_request
    row = self.row(key)
    if row is None or not row.available or row.value == value:
      return bool(row is not None and row.value == value)
    request = row_request(row, value)
    if confirmed:
      request = replace(request, confirmation=True)
    try:
      return bool(self._apply(request))
    finally:
      self.refresh()

  def set_on(self, key: str, on: bool, confirmed: bool = False) -> bool:
    return self.set(key, "On" if on else "Off", confirmed)

  def set_number(self, key: str, value: float, confirmed: bool = False) -> bool:
    row = self.row(key)
    step = float(row.step) if row is not None and row.step else 0.0
    text = f"{value:g}" if step % 1 else str(round(value))
    return self.set(key, text, confirmed)


class StarPilotOwners:
  """StarPilot 7's settings owners, with its settings screen's permissions. shown() says whether settings are open."""

  def __init__(self, ui: Any, shown: Callable[[], bool]):
    import os
    from openpilot.starpilot.drive_state.evidence import PhysicalSource
    from openpilot.starpilot.ui.feature_settings_owner import FeatureSettingsOwner
    from openpilot.starpilot.ui.runtime_snapshot import RuntimeSnapshotAdapter
    self._ui, self._shown = ui, shown
    self._adapter = RuntimeSnapshotAdapter(ui)
    self._physical = PhysicalSource(ui.sm)

    def vision_development() -> bool:
      from openpilot.starpilot.speed_limits.vision_gate import diagnostic_choice_enabled
      return bool(diagnostic_choice_enabled(os.environ, ui.CP))

    self.owner = FeatureSettingsOwner(ui.params, self.feature_authority, vehicle_fingerprint=lambda: getattr(ui.CP, "carFingerprint", None),
                                      vehicle_params=lambda: ui.CP, vision_development=vision_development)
    self._pages: dict[str, FeatureRows] = {}

  def rows(self, page: str) -> FeatureRows:
    """One FeatureRows per page, shared by every model that reads it. "sentry" is StarPilot's Sentry owner."""
    if page not in self._pages:
      if page == "sentry":
        from openpilot.starpilot.ui.sentry_owner import SentryOwner
        sentry = SentryOwner(self._ui.params, self.configuration_allowed)
        self._pages[page] = FeatureRows(sentry.snapshot, sentry.apply)
      else:
        def read() -> Any:
          return self.owner.snapshot(page, parked=self.configuration_allowed(), system_long=self.feature_authority("long"),
                                     lateral_context=self.feature_authority("lane"), metric=self.metric(),
                                     configure_while_driving=self.preference_authority())
        self._pages[page] = FeatureRows(read, self.owner.apply)
    return self._pages[page]

  def metric(self) -> bool:
    return bool(self._ui.is_metric)

  def confirmed_offroad(self) -> bool:
    return bool(self._ui.is_offroad() and self._adapter.confirmed_offroad())

  def configuration_allowed(self) -> bool:
    """Parked-only settings: StarPilot confirms the car is off, or parked with fresh evidence."""
    try:
      return self.confirmed_offroad() or bool(self._physical.allowed())
    except Exception:
      return False

  def preference_authority(self) -> bool:
    """Driver preferences change only while settings are open, and never in replay or projection."""
    return bool(self._shown() and self._ui.replay_clock is None and not getattr(self._ui, "projection_read_only", False))

  def feature_authority(self, group: str) -> bool:
    """StarPilot's settings screen's rule for each group (runtime_app.StarShellSession._feature_authority), without its
    onroad favorites, which Tandem doesn't offer."""
    allowed = self.preference_authority()
    if group == "preferences":
      return allowed
    if group == "parked_preferences":
      return allowed and self.configuration_allowed()
    cp = self._ui.CP
    if cp is None or not getattr(cp, "carFingerprint", "") or not allowed:
      return False
    vehicle_ok = not cp.notCar and not cp.passive and not cp.dashcamOnly
    if group == "toyota_cruise":
      from openpilot.starpilot.controllers.toyota_cruise import capability
      return capability(cp) is not None
    if group == "vehicle":
      from opendbc.car.toyota.interface import toyota_auto_hold_supported
      return bool(toyota_auto_hold_supported(cp))
    if group == "lane_change":
      return vehicle_ok
    if group == "switchback_wheel":
      from openpilot.starpilot.feature_capabilities import lateral_supported
      return bool(lateral_supported(cp))
    if group in ("conditional", "conditional_wheel", "long_output", "slc"):
      return bool(cp.openpilotLongitudinalControl and vehicle_ok)
    if group in ("aol_wheel", "lane", "torque", "aol"):
      return vehicle_ok
    if group in ("long",):
      return bool(cp.openpilotLongitudinalControl and vehicle_ok)
    return False
