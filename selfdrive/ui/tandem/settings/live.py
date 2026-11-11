"""Live car and device state that settings screens react to: engaged, parked, and whether openpilot controls gas and brake.

Live reads upstream's ui_state on the device. Tests pass FakeLive, or any object with these methods.
"""
from __future__ import annotations


class Live:
  """The car's live state the settings need: engaged, offroad, and whether openpilot controls speed."""

  def __init__(self) -> None:
    from openpilot.selfdrive.ui.ui_state import ui_state
    self._ui = ui_state

  def engaged(self) -> bool:
    return bool(self._ui.engaged)

  def offroad(self) -> bool:
    return bool(self._ui.is_offroad())

  def has_longitudinal(self) -> bool:
    return bool(self._ui.has_longitudinal_control)


class FakeLive:
  """Live state set by hand, for tests and renders."""

  def __init__(self, engaged: bool = False, offroad: bool = True, longitudinal: bool = True):
    self.is_engaged, self.is_offroad, self.longitudinal = engaged, offroad, longitudinal

  def engaged(self) -> bool:
    return self.is_engaged

  def offroad(self) -> bool:
    return self.is_offroad

  def has_longitudinal(self) -> bool:
    return self.longitudinal
