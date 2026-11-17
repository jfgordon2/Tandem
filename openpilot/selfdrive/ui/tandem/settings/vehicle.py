"""Vehicle: the detected car, choosing it by hand, door locks, and what the steering wheel buttons do.

StarPilot 7 keeps the chosen car in its vehicle selection owner (Auto keeps fingerprinting), the wheel buttons on its
"wheel" settings page and the car-specific options on its "vehicle" page; both pages list only what the car has.
"More for your car" shows the vehicle page's rows, each change confirmed first. Toyota door locks have no settings row,
so they're written the way StarPilot's Galaxy writes them (ToyotaDoors): parked, for a Toyota, against the saved bytes.
StarPilot 7 dropped the lock timer.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol, TYPE_CHECKING

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Card, Columns, Inline, Label, Sized, Stack
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.layout import FILL, column, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, OptionList, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.pages import FillPage, PanelPage
from openpilot.selfdrive.ui.tandem.settings.speed_steering import Rows
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

WHEEL, VEHICLE = "wheel", "vehicle"


@dataclass(frozen=True)
class CarOption:
  """A model in the car picker."""
  value: str     # StarPilot's platform, e.g. TOYOTA_RAV4H
  label: str     # e.g. "Toyota RAV4 Hybrid 2019-21"


@dataclass(frozen=True)
class WheelButton:
  """A steering wheel button press StarPilot can give an action: its name and StarPilot's row key."""
  name: str
  key: str


class CarSelection(Protocol):
  """StarPilot's vehicle selection owner."""

  def snapshot(self) -> Any: ...                                       # .raw, .readable, .valid, .platform
  def choices(self) -> tuple[Any, ...]: ...                            # .platform, .make, .label
  def choose(self, expected_raw: bytes | None, platform: str | None) -> Any: ...


class Doors(Protocol):
  """Toyota door locks: whether the car has them, and lock on drive and unlock on park."""

  def available(self) -> bool: ...
  def get(self, key: str) -> bool: ...
  def set(self, key: str, on: bool) -> bool: ...


class Vehicle:
  """Driving › Vehicle: the car (detected or chosen), door locks, and the wheel buttons' actions.

  Args:
    selection: StarPilot's vehicle selection owner.
    rows: StarPilot's settings pages.
    doors: Toyota door locks.
    detected: The fingerprinted car's platform, or "" before the first drive.
  """

  def __init__(self, selection: CarSelection, rows: Rows, doors: Doors, detected: Callable[[], str]):
    self._selection = selection
    self._rows = rows
    self.doors = doors
    self._detected = detected

  def _choice(self, platform: str) -> Any | None:
    return next((c for c in self._selection.choices() if c.platform == platform), None)

  def car(self) -> str:
    choice = self._choice(self._selection.snapshot().platform or self._detected())
    return choice.label if choice is not None else N_("Detected on the first drive")

  def make(self) -> str:
    choice = self._choice(self._selection.snapshot().platform or self._detected())
    return choice.make if choice is not None else ""

  def makes(self) -> list[str]:
    return list(dict.fromkeys(c.make for c in self._selection.choices()))

  def models(self, make: str) -> list[CarOption]:
    return [CarOption(c.platform, c.label) for c in self._selection.choices() if c.make == make]

  def current_platform(self) -> str:
    return self._selection.snapshot().platform or self._detected()

  @property
  def manual(self) -> bool:
    return self._selection.snapshot().platform is not None

  def choose(self, option: CarOption) -> bool:
    """Saving a car turns off automatic detection, as on StarPilot's screen; it applies on the next start."""
    return bool(self._selection.choose(self._selection.snapshot().raw, option.value).committed)

  def use_detection(self) -> None:
    self._selection.choose(self._selection.snapshot().raw, None)

  @property
  def auto_lock(self) -> bool:
    return self.doors.get("LockDoors")

  def set_auto_lock(self, on: bool) -> None:
    self.doors.set("LockDoors", on)

  @property
  def auto_unlock(self) -> bool:
    return self.doors.get("UnlockDoors")

  def set_auto_unlock(self, on: bool) -> None:
    self.doors.set("UnlockDoors", on)

  def buttons(self) -> list[WheelButton]:
    """The wheel presses StarPilot lists for this car."""
    return [WheelButton(r.label, r.key) for r in self._rows(WHEEL).state().rows if r.key.startswith("wheel:")]

  def actions(self, button: WheelButton) -> list[str]:
    row = self._rows(WHEEL).row(button.key)
    return list(row.choices) if row is not None else []

  def action_name(self, button: WheelButton) -> str:
    return self._rows(WHEEL).value(button.key, N_("Car default"))

  def button_editable(self, button: WheelButton) -> bool:
    return self._rows(WHEEL).available(button.key)

  def set_action(self, button: WheelButton, action: str) -> None:
    self._rows(WHEEL).set(button.key, action)

  def buttons_summary(self) -> str:
    return t_("{} buttons", len(self.buttons())) if self.buttons() else N_("Car default buttons")

  def extras(self) -> list[Any]:
    """StarPilot's options for this car (its vehicle page), as rows."""
    return [r for r in self._rows(VEHICLE).state().rows if r.key]

  def set_extra(self, key: str, value: str) -> None:
    """A car option changes only after the driver confirms it, so it goes to StarPilot as confirmed."""
    self._rows(VEHICLE).set(key, value, confirmed=True)

  def extra_value(self, key: str) -> str:
    return self._rows(VEHICLE).value(key)

  def extra_editable(self, key: str) -> bool:
    return self._rows(VEHICLE).available(key)


class CarPicker(Component):
  """Makes on the left, that make's models on the right."""
  grow_touch_target = False

  def __init__(self, vehicle: Vehicle):
    super().__init__()
    self._vehicle = vehicle
    makes = vehicle.makes()
    self._makes = makes
    self._make = makes.index(vehicle.make()) if vehicle.make() in makes else 0
    self._model = self._current_model()
    self._make_list = self._child(OptionList(makes, lambda: self._make, self._pick_make))
    self._model_list: OptionList | None = None
    self._built_for = -1

  def _options(self) -> list[CarOption]:
    return self._vehicle.models(self._makes[self._make]) if self._makes else []

  def _current_model(self) -> int:
    platform = self._vehicle.current_platform()
    return next((i for i, o in enumerate(self._options()) if o.value == platform), -1)

  def _pick_make(self, index: int) -> None:
    self._make = index
    self._model = -1

  def _pick_model(self, index: int) -> None:
    self._model = index

  def save(self) -> bool:
    options = self._options()
    if not 0 <= self._model < len(options):
      return False
    return self._vehicle.choose(options[self._model])

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(330)

  def _render(self, rect: rl.Rectangle) -> None:
    if self._built_for != self._make:
      self._built_for = self._make
      self._model_list = OptionList([o.label for o in self._options()], lambda: self._model, self._pick_model)
    left, right = row(rect, [T.px(260), FILL], T.px(18))
    for title, area, widget in ((N_("MAKE"), left, self._make_list), (N_("MODEL"), right, self._model_list)):
      caption, body = column(area, [T.px(28), FILL], T.px(6))
      draw.caption(caption, title)
      draw.fill(body, T.SURFACE_1, T.RADIUS_CARD)
      if widget is not None:
        widget.render(body)


def vehicle_page(vehicle: Vehicle, window: SettingsWindow, open_more: Callable[[], None]) -> Widget:
  """Driving › Vehicle's page: the car, door locks, its buttons' actions, and More options."""
  def choose_car() -> None:
    picker = CarPicker(vehicle)

    def save() -> None:
      if picker.save():
        window.dismiss()
    window.present(Sheet(N_("Choose your car"), picker,
                         subtitle=N_("Only needed if detection picked the wrong car. Choosing turns off automatic detection."),
                         actions=[Button(N_("Cancel"), window.dismiss), Button(N_("Save"), save, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))

  def pick_action(button: WheelButton) -> Callable[[], None]:
    def show() -> None:
      actions = vehicle.actions(button)

      def select(index: int) -> None:
        vehicle.set_action(button, actions[index])
        window.dismiss()
      window.present(Sheet(button.name, OptionList(actions, lambda: actions.index(vehicle.action_name(button))
                                                   if vehicle.action_name(button) in actions else 0, select),
                           subtitle=N_("What this button does while driving"), on_dismiss=window.dismiss))
    return show

  car = Card([
    Label(N_("YOUR CAR"), color=T.ACCENT_TEXT, caption=True),
    Label(vehicle.car, T.font_px(26), weight=T.FONT_EXTRABOLD),
    Label(lambda: N_("Chosen manually") if vehicle.manual else N_("Detected automatically"), T.font_px(15),
          lambda: T.TEXT_TERTIARY if vehicle.manual else T.SUCCESS_TEXT, T.FONT, icon=lambda: None if vehicle.manual else "check"),
    SPACER,
    Inline(Button(lambda: N_("Use detection instead") if vehicle.manual else N_("Wrong car? Choose it manually"),
                  lambda: vehicle.use_detection() if vehicle.manual else choose_car(), ButtonStyle.GHOST, height=T.px(40),
                  font_size=T.font_px(16))),
  ], gap=T.px(10), padding=(T.px(22), T.px(22)))
  lock = Sized(ListPanel([SettingRow(N_("Auto-Lock Doors"), N_("Locks when you shift out of park"),
                                     Switch(lambda: vehicle.auto_lock, vehicle.set_auto_lock)),
                          SettingRow(N_("Auto-Unlock Doors"), N_("Unlocks when you shift into park"),
                                     Switch(lambda: vehicle.auto_unlock, vehicle.set_auto_unlock))]),
               T.px(152))
  lock.set_visible(vehicle.doors.available)

  def buttons() -> list[Widget]:
    rows: list[Widget] = []
    for b in vehicle.buttons():
      line = SettingRow(b.name, "", ValueButton(partial(vehicle.action_name, b), pick_action(b)))
      line.set_enabled(partial(vehicle.button_editable, b))
      rows.append(line)
    return rows or [Text(N_("StarPilot lists your car's buttons once it's detected."))]

  wheel = ListPanel([
    *buttons(),
    SettingRow(N_("More for your car"), N_("Features specific to your make and model"), on_click=open_more),
  ], title=N_("Steering Wheel Buttons"), subtitle=N_("Preset for your car. Tap a button to change what it does."), title_size=T.font_px(20))
  return FillPage(Columns([Stack([car, lock], gap=T.px(14), grow=0), wheel], [1, 1.35]))


def _is_on(vehicle: Vehicle, key: str) -> bool:
  return vehicle.extra_value(key) == "On"


def extras_page(vehicle: Vehicle, window: SettingsWindow) -> Widget:
  """More for your car: StarPilot's options for this car, a switch or a choice each; every change asks first."""
  from openpilot.selfdrive.ui.tandem.overlays import Dialog
  from openpilot.selfdrive.ui.tandem.controls import Tone
  from openpilot.system.ui.widgets import DialogResult

  def ask(title: str, message: str, then: Callable[[], None]) -> None:
    def done(result: DialogResult) -> None:
      window.dismiss()
      if result == DialogResult.CONFIRM:
        then()
    window.present(Dialog(title, message or N_("This changes how StarPilot drives this car."), N_("Change"), done, tone=Tone.ACCENT,
                          glyph=lambda r, c, s: draw.icon(r, "warning", c, s)))

  def flipped(extra: Any) -> Callable[[bool], None]:
    return lambda on: ask(t_("Turn {} {}?", N_("on") if on else N_("off"), extra.label), extra.reason,
                          lambda: vehicle.set_extra(extra.key, "On" if on else "Off"))

  def choice_sheet(extra: Any) -> Callable[[], None]:
    def show() -> None:
      choices = list(extra.choices)

      def pick(index: int) -> None:
        window.dismiss()
        ask(t_("Change {}?", extra.label), extra.reason, lambda: vehicle.set_extra(extra.key, choices[index]))
      window.present(Sheet(extra.label, OptionList(choices, lambda: choices.index(vehicle.extra_value(extra.key))
                                                   if vehicle.extra_value(extra.key) in choices else 0, pick),
                           subtitle=extra.reason, on_dismiss=window.dismiss))
    return show

  rows: list[Widget] = []
  for extra in vehicle.extras():
    if tuple(extra.choices) == ("Off", "On"):
      line = SettingRow(extra.label, extra.reason, Switch(partial(_is_on, vehicle, extra.key), flipped(extra)))
    elif extra.choices:
      line = SettingRow(extra.label, extra.reason, ValueButton(partial(vehicle.extra_value, extra.key), choice_sheet(extra)))
    else:
      continue   # numbers and actions stay on StarPilot's own screens
    line.set_enabled(partial(vehicle.extra_editable, extra.key))
    rows.append(line)
  if not rows:
    rows.append(Text(N_("Nothing extra for this car. Everything it supports is on the Vehicle page.")))
  return PanelPage(ListPanel(rows, title=N_("More for your car"), subtitle=N_("Options only some makes and models have")))


class ToyotaDoors:
  """Toyota door locks, written as StarPilot's Galaxy writes them: parked, for a Toyota, and only if unchanged since read.

  Args:
    params: StarPilot's Params.
    cp: The car's CarParams, or None before it's known.
    parked: Whether StarPilot confirms the car is parked.
  """
  KEYS = ("LockDoors", "UnlockDoors")
  MAX_BYTES = 128

  def __init__(self, params: Any, cp: Callable[[], Any], parked: Callable[[], bool]):
    self._params, self._cp, self._parked = params, cp, parked

  def _capability(self) -> Any:
    from openpilot.starpilot.galaxy.toyota_tools import capability
    return capability(self._cp())

  def available(self) -> bool:
    return self._capability() is not None

  def get(self, key: str) -> bool:
    from openpilot.starpilot.saved_source import read_saved
    raw, readable = read_saved(self._params, key, self.MAX_BYTES)
    return bool(readable and raw == b"1")

  def set(self, key: str, on: bool) -> bool:
    """Saves the choice; StarPilot applies it on the next start."""
    from openpilot.starpilot.saved_document import commit_exact
    from openpilot.starpilot.saved_source import read_saved
    if key not in self.KEYS:
      return False
    raw, readable = read_saved(self._params, key, self.MAX_BYTES)
    capability = self._capability()
    if not readable or raw not in (None, b"0", b"1") or capability is None:
      return False

    def authorized() -> bool:
      return bool(self._parked() and self._capability() == capability)
    result = commit_exact(self._params, key=key, max_bytes=self.MAX_BYTES, raw=b"1" if on else b"0", expected=raw,
                          authorized=authorized, temp_prefix=".tandem-doors-")
    return bool(result.committed and result.verified)
