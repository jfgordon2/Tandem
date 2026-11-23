"""Device › Power (design/devicepower.html): StarPilot 7's parked power limits, aggressive cooling and drive state.

StarPilot decides what's allowed: its power owner (starpilot/ui/power_owner.py) saves the parked limits only after the
driver confirms, its feature owner has Aggressive Cooling on the comma 3 and 3X (the "power" page), and its drive-state
owner forces Offroad or Onroad, asking first before Offroad stops driving services. As on StarPilot's own System page,
all three change whenever settings are open.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.controls import Segmented, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.selfdrive.ui.tandem.overlays import Dialog, DialogResult, Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, OptionList, SettingRow
from openpilot.selfdrive.ui.tandem.settings.speed_steering import Rows

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

ENABLED, HOURS, VOLTS = "power:enabled", "power:hours", "power:volts"   # starpilot/ui/power_owner.py
CUSTOM = "Custom limits"
COOLING = "AggressiveCoolingEnabled"   # starpilot/ui/feature_settings_owner.AGGRESSIVE_COOLING_KEY
PARKED_POWER = [N_("Stock"), N_("Custom")]
ROW_HEIGHT = T.px(58)   # all five rows fit without scrolling, as in the mock
DRIVE_STATES = [("auto", N_("Auto")), ("offroad", N_("Offroad")), ("onroad", N_("Onroad"))]


class Power:
  """The Power page's state and changes, over StarPilot's owners.

  Args:
    rows: StarPilot's settings pages: "parked_power" (its power owner) and "power" (Aggressive Cooling).
    drive: StarPilot's DriveStateControl, or None where there's none.
    allowed: Whether settings may change now (StarPilot's settings authority).
    car_on: Whether driving services run now, so forcing Offroad would stop them.
  """

  def __init__(self, rows: Rows, drive: Any, allowed: Callable[[], bool], car_on: Callable[[], bool]):
    self._rows, self._drive, self._allowed, self._car_on = rows, drive, allowed, car_on

  # Parked power

  @property
  def custom(self) -> bool:
    return self._rows("parked_power").value(ENABLED) == CUSTOM

  def parked_editable(self) -> bool:
    return self._rows("parked_power").available(ENABLED)

  def limits_editable(self) -> bool:
    return self.custom and self._rows("parked_power").available(HOURS)

  def hours(self) -> str:
    return self._rows("parked_power").value(HOURS)

  def volts(self) -> str:
    return self._rows("parked_power").value(VOLTS)

  def choices(self, key: str) -> list[str]:
    row = self._rows("parked_power").row(key)
    return list(row.choices) if row is not None else []

  def question(self, key: str, value: str) -> str:
    """What the confirmation asks before StarPilot saves a parked limit."""
    if key == ENABLED:
      if value == CUSTOM:
        return t_("Turn the comma off after {} parked, or below {}? Other protections can turn it off sooner.", self.hours(), self.volts())
      return N_("Go back to the stock parked limits?")
    if key == HOURS:
      return t_("Turn the comma off after {} parked? Other protections can turn it off sooner.", value)
    return t_("Turn the comma off below {} while parked?", value)

  def save(self, key: str, value: str) -> bool:
    """Saves a confirmed parked limit through StarPilot's power owner; True when it saved."""
    return self._rows("parked_power").set(key, value, confirmed=True)

  # Cooling

  def cooling_offered(self) -> bool:
    """StarPilot offers Aggressive Cooling only on the comma 3 and 3X."""
    return self._rows("power").row(COOLING) is not None

  @property
  def cooling(self) -> bool:
    return self._rows("power").on(COOLING)

  def set_cooling(self, on: bool) -> None:
    self._rows("power").set_on(COOLING, on)

  def cooling_editable(self) -> bool:
    return self._rows("power").available(COOLING)

  # Drive state

  def drive_status(self) -> dict | None:
    try:
      return self._drive.snapshot() if self._drive is not None else None
    except (OSError, RuntimeError):
      return None

  @property
  def drive_state(self) -> int:
    status = self.drive_status()
    mode = status["mode"] if status else "auto"
    return next((i for i, (key, _) in enumerate(DRIVE_STATES) if key == mode), 0)

  def drive_editable(self) -> bool:
    status = self.drive_status()
    return bool(status and status["available"] and self._allowed())

  def needs_offroad_confirmation(self, index: int) -> bool:
    """Forcing Offroad while driving services run stops them, so StarPilot asks first."""
    status = self.drive_status()
    return DRIVE_STATES[index][0] == "offroad" and (self._car_on() or bool(status and status["effective"] == "onroad"))

  def set_drive_state(self, index: int) -> bool:
    """Asks StarPilot's drive-state owner for a mode, bound to the revision last read; True when it changed."""
    status = self.drive_status()
    if status is None or not status["available"]:
      return False
    try:
      self._drive.change(DRIVE_STATES[index][0], status["revision"], self._allowed)
    except (ValueError, OSError, RuntimeError):   # StarPilot's drive_state.owner.Rejected is a ValueError
      return False
    return True


def power_panel(model: Power, window: SettingsWindow) -> ListPanel:
  """The Power page."""
  def confirm(key: str, value: str) -> None:
    def done(result: DialogResult) -> None:
      window.dismiss()
      if result == DialogResult.CONFIRM:
        model.save(key, value)
    window.present(Dialog(N_("Parked Power"), model.question(key, value), N_("Save"), done))

  def pick(key: str, title: str) -> None:
    choices = model.choices(key)
    current = model.hours() if key == HOURS else model.volts()

    def chosen(index: int) -> None:
      window.dismiss()
      if choices[index] != current:
        confirm(key, choices[index])
    window.present(Sheet(title, OptionList(choices, choices.index(current) if current in choices else 0, chosen),
                         on_dismiss=window.dismiss))

  def set_parked(index: int) -> None:
    value = CUSTOM if index == 1 else "Stock"
    if value != (CUSTOM if model.custom else "Stock"):
      confirm(ENABLED, value)

  def set_drive(index: int) -> None:
    if index == model.drive_state:
      return
    if not model.needs_offroad_confirmation(index):
      model.set_drive_state(index)
      return

    def done(result: DialogResult) -> None:
      window.dismiss()
      if result == DialogResult.CONFIRM:
        model.set_drive_state(index)
    window.present(Dialog(N_("Force Offroad"), N_("Switch to Offroad and stop driving services?"), N_("Force Offroad"), done))

  parked = SettingRow(N_("Parked Power"), N_("Turn the comma off after a long park or a low battery"),
                      Segmented(PARKED_POWER, lambda: 1 if model.custom else 0, set_parked), height=ROW_HEIGHT)
  parked.set_enabled(model.parked_editable)
  hours = SettingRow(N_("Maximum Parked Time"), N_("Then it turns off, sparing the car's battery"),
                     ValueButton(model.hours, lambda: pick(HOURS, N_("Maximum Parked Time"))), height=ROW_HEIGHT)
  hours.set_enabled(model.limits_editable)
  volts = SettingRow(N_("Low-Voltage Cutoff"), N_("Turns off sooner if the battery drops this low"),
                     ValueButton(model.volts, lambda: pick(VOLTS, N_("Low-Voltage Cutoff"))), height=ROW_HEIGHT)
  volts.set_enabled(model.limits_editable)
  rows = [parked, hours, volts]
  if model.cooling_offered():
    cooling = SettingRow(N_("Aggressive Cooling"), N_("Fan runs sooner and harder: 10 to 16 °C cooler, more noise"),
                         Switch(lambda: model.cooling, model.set_cooling), height=ROW_HEIGHT)
    cooling.set_enabled(model.cooling_editable)
    rows.append(cooling)
  drive = SettingRow(N_("Drive State"), N_("Auto follows the car; force offroad or onroad for testing"),
                     Segmented([name for _, name in DRIVE_STATES], lambda: model.drive_state, set_drive), height=ROW_HEIGHT)
  drive.set_enabled(model.drive_editable)
  rows.append(drive)
  return ListPanel(rows, title=N_("Power"), subtitle=N_("The car's battery while parked, cooling, and drive state"),
                   footnote=N_("New parked limits are confirmed before they save."))
