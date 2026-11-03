"""Vehicle: the detected car, choosing it by hand, auto-lock, and what the steering wheel buttons do.

"More for your car" lists StarPilot's car-specific options (GM, Subaru, Toyota, Bolt, Jeep, Hyundai/Kia CAN FD, panda
flashing) for the detected car only, on StarPilot's params and handlers.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Card, Columns, Inline, Label, Sized, Stack
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.layout import FILL, column, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, OptionList, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.pages import FillPage, PanelPage
from openpilot.selfdrive.ui.tandem.settings.favorites import favorite_action_names
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.i18n import N_, t_


# StarPilot's button action ids, named for what they do.
ACTION_NAMES = {0: N_("Car default"), 1: N_("Change driving style"), 2: N_("Coast"), 3: N_("Pause steering"), 4: N_("Pause gas and brake"),
                5: N_("Switch experimental mode"), 6: N_("Traffic mode"), 7: N_("Switchback mode"), 8: N_("Save a clip"), 9: N_("Always-on steering"),
                10: N_("Match the speed limit"), 11: N_("Favorite 1"), 12: N_("Favorite 2"), 13: N_("Favorite 3")}


@dataclass(frozen=True)
class CarOption:
  value: str     # CarModel, the fingerprint
  label: str     # CarModelName, e.g. "RAV4 Hybrid 2019-21"


@dataclass(frozen=True)
class WheelButton:
  name: str
  press: str
  key: str
  cruise_main: bool = False


class CarCatalog(Protocol):
  def makes(self) -> list[str]: ...
  def models(self, make: str) -> list[CarOption]: ...
  def actions(self, button: WheelButton) -> list[tuple[int, str]]: ...
  def buttons(self) -> list[WheelButton]: ...
  def has_auto_lock(self) -> bool: ...


class Vehicle:
  def __init__(self, store: SettingsStore, catalog: CarCatalog):
    self._store = store
    self.catalog = catalog

  def car(self) -> str:
    return self._store.get_str("CarModelName") or N_("Detected on the first drive")

  def make(self) -> str:
    return self._store.get_str("CarMake")

  @property
  def manual(self) -> bool:
    return self._store.get_bool("ForceFingerprint")

  def choose(self, make: str, option: CarOption) -> None:
    """Saving a car turns off automatic detection, as on StarPilot's screen."""
    self._store.write({"ForceFingerprint": True, "CarMake": make, "CarModel": option.value, "CarModelName": option.label})

  def use_detection(self) -> None:
    self._store.write({"ForceFingerprint": False})

  @property
  def auto_lock(self) -> bool:
    return self._store.get_bool("LockDoors")

  def set_auto_lock(self, on: bool) -> None:
    self._store.write({"LockDoors": on})

  def action(self, button: WheelButton) -> int:
    return self._store.get_int(button.key)

  def action_name(self, button: WheelButton) -> str:
    current = self.action(button)
    return next((name for i, name in self.catalog.actions(button) if i == current), ACTION_NAMES[0])

  def set_action(self, button: WheelButton, action: int) -> None:
    self._store.write({button.key: action})

  def buttons_summary(self) -> str:
    return N_("Buttons customized") if any(self.action(b) for b in self.catalog.buttons()) else N_("Car default buttons")


class CarPicker(Component):
  """Makes on the left, that make's models on the right."""
  grow_touch_target = False

  def __init__(self, vehicle: Vehicle):
    super().__init__()
    self._vehicle = vehicle
    makes = vehicle.catalog.makes()
    self._makes = makes
    self._make = makes.index(vehicle.make()) if vehicle.make() in makes else 0
    self._model = self._current_model()
    self._make_list = self._child(OptionList(makes, lambda: self._make, self._pick_make))
    self._model_list: OptionList | None = None
    self._built_for = -1

  def _options(self) -> list[CarOption]:
    return self._vehicle.catalog.models(self._makes[self._make]) if self._makes else []

  def _current_model(self) -> int:
    name = self._vehicle._store.get_str("CarModelName")
    return next((i for i, o in enumerate(self._options()) if o.label == name), -1)

  def _pick_make(self, index: int) -> None:
    self._make = index
    self._model = -1

  def _pick_model(self, index: int) -> None:
    self._model = index

  def save(self) -> bool:
    options = self._options()
    if not 0 <= self._model < len(options):
      return False
    self._vehicle.choose(self._makes[self._make], options[self._model])
    return True

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(330)

  def _render(self, rect: rl.Rectangle):
    if self._built_for != self._make:
      self._built_for = self._make
      self._model_list = OptionList([o.label for o in self._options()], lambda: self._model, self._pick_model)
    left, right = row(rect, [T.px(260), FILL], T.px(18))
    for title, area, widget in ((N_("MAKE"), left, self._make_list), (N_("MODEL"), right, self._model_list)):
      caption, body = column(area, [T.px(28), FILL], T.px(6))
      draw.caption(caption, title)
      draw.fill(body, T.SURFACE_1, T.RADIUS_CARD)
      widget.render(body)


def vehicle_page(vehicle: Vehicle, window, open_more: Callable[[], None]) -> Widget:
  def choose_car():
    picker = CarPicker(vehicle)

    def save():
      if picker.save():
        window.dismiss()
    window.present(Sheet(N_("Choose your car"), picker,
                         subtitle=N_("Only needed if detection picked the wrong car. Choosing turns off automatic detection."),
                         actions=[Button(N_("Cancel"), window.dismiss), Button(N_("Save"), save, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))

  def pick_action(button: WheelButton) -> Callable[[], None]:
    def show():
      actions = vehicle.catalog.actions(button)
      ids = [i for i, _ in actions]

      def select(index: int):
        vehicle.set_action(button, ids[index])
        window.dismiss()
      window.present(Sheet(f"{button.name} · {button.press}", OptionList([name for _, name in actions],
                                                                         lambda: ids.index(vehicle.action(button)) if vehicle.action(button) in ids else 0,
                                                                         select),
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
  lock = Sized(ListPanel([SettingRow(N_("Auto-Lock Doors"), N_("Locks when you shift out of park"), Switch(lambda: vehicle.auto_lock,
                                                                                                   vehicle.set_auto_lock))]),
               T.px(76))
  lock.set_visible(vehicle.catalog.has_auto_lock)
  buttons = [SettingRow(f"{b.name}", b.press, ValueButton(lambda b=b: vehicle.action_name(b), pick_action(b)))
             for b in vehicle.catalog.buttons()]
  wheel = ListPanel([
    *buttons,
    SettingRow(N_("More for your car"), N_("Features specific to your make and model"), on_click=open_more),
  ], title=N_("Steering Wheel Buttons"), subtitle=N_("Preset for your car. Tap a button to change what it does."), title_size=T.font_px(20))
  return FillPage(Columns([Stack([car, lock], gap=T.px(14), grow=0), wheel], [1, 1.35]))


class UpstreamCars:
  """CarCatalog backed by StarPilot's fingerprint list, button actions and detected car state."""

  def __init__(self):
    from openpilot.selfdrive.ui.layouts.settings.starpilot import vehicle as v
    from openpilot.selfdrive.ui.lib.fingerprint_catalog import get_fingerprint_catalog
    from openpilot.selfdrive.ui.lib.starpilot_state import starpilot_state
    self._v = v
    self._state = starpilot_state
    self._makes, self._by_make, _, _ = get_fingerprint_catalog()

  def makes(self) -> list[str]:
    return list(self._makes)

  def models(self, make: str) -> list[CarOption]:
    return [CarOption(o.value, o.label) for o in self._by_make.get(make, ())]

  def actions(self, button: WheelButton) -> list[tuple[int, str]]:
    """The same choices StarPilot offers, without the developer-only Pulse and Glide."""
    longitudinal = self._state.car_state.hasOpenpilotLongitudinal
    if button.cruise_main:
      allowed = {0, 9, 10, 11, 12, 13}
    else:
      allowed = set(range(9)) | {11, 12, 13} | ({9} if button.key == "LKASButtonControl" else set())
    names = ACTION_NAMES | {11 + i: name for i, name in enumerate(favorite_action_names(self._state.params))}
    return [(o["id"], names.get(o["id"], o["name"])) for o in self._v.ACTION_OPTIONS
            if o["id"] in allowed and (longitudinal or not o.get("requires_longitudinal", False))]

  def buttons(self) -> list[WheelButton]:
    cs = self._state.car_state
    buttons = [WheelButton(N_("Distance"), N_("Press"), "DistanceButtonControl"),
               WheelButton(N_("Distance"), N_("Long press"), "LongDistanceButtonControl")]
    if not cs.isSubaru:
      buttons.append(WheelButton(N_("LKAS"), N_("Press"), "LKASButtonControl"))
    buttons.append(WheelButton(N_("Cruise main"), N_("Press"), "MainCruiseButtonControl", cruise_main=True))
    if cs.isBolt and cs.hasPedal and self._state.params.get_bool("RemapCancelToDistance"):
      buttons.append(WheelButton(N_("Cancel"), N_("Press"), "CancelButtonControl"))   # "Use Cancel as a button" in More for your car
    if cs.hasModeStarButtons:
      buttons += [WheelButton(N_("Mode"), N_("Press"), "ModeButtonControl"), WheelButton(N_("Star"), N_("Press"), "StarButtonControl")]
    return buttons

  def has_auto_lock(self) -> bool:
    return bool(self._state.car_state.isToyota)


# ── More for your car: StarPilot's car-specific options, shown only for the cars they apply to ──

@dataclass(frozen=True)
class CarExtra:
  key: str
  title: str
  line: str
  kind: str = "toggle"     # "toggle", "flash" (needs a panda firmware update, then a restart) or "timer"
  warn: str = ""           # turning it on asks first with this message


LOCK_TIMES = [(0, N_("Never")), (10, N_("10 s")), (30, N_("30 s")), (60, N_("1 min")), (120, N_("2 min")), (300, N_("5 min"))]


class CarExtras(Protocol):
  def extras(self) -> list[CarExtra]: ...
  def value(self, key: str) -> bool: ...
  def toggle(self, key: str) -> None: ...     # upstream's toggle, with its side effects (a restart, a migration)
  def flash(self, key: str) -> None: ...      # upstream's panda firmware toggle: flashes, then restarts
  def timer(self) -> int: ...
  def set_timer(self, seconds: int) -> None: ...


def extras_page(extras: CarExtras, window) -> Widget:
  """More for your car: a switch per option, a timer as a picker; options that restart or flash ask first."""
  from openpilot.selfdrive.ui.tandem.overlays import Dialog
  from openpilot.selfdrive.ui.tandem.controls import Tone
  from openpilot.system.ui.widgets import DialogResult

  def ask(title: str, message: str, label: str, then: Callable[[], None], danger: bool = False) -> None:
    def done(result) -> None:
      window.dismiss()
      if result == DialogResult.CONFIRM:
        then()
    window.present(Dialog(title, message, label, done, tone=Tone.DANGER if danger else Tone.ACCENT,
                          glyph=lambda r, c, s: draw.icon(r, "warning", c, s)))

  def flipped(extra: CarExtra) -> Callable[[bool], None]:
    def change(on: bool) -> None:
      if extra.kind == "flash":
        def flash() -> None:
          extras.flash(extra.key)
          window.present(Dialog(N_("Updating the panda"), N_("The device restarts when it's done. Keep the car on until then."), "OK",
                                lambda r: window.dismiss(), cancel_label=None))
        ask(f"{N_('Turn on') if on else N_('Turn off')} {extra.title.lower()}?",
            N_("This needs a panda firmware update, and the device restarts when it's done."), N_("Update and restart"), flash)
      elif on and extra.warn:
        ask(f"{extra.title}?", extra.warn, N_("Turn On"), lambda: extras.toggle(extra.key), danger=True)
      else:
        extras.toggle(extra.key)
    return change

  def timer_sheet() -> None:
    times = list(LOCK_TIMES)
    if extras.timer() not in [s for s, _ in times]:
      times.append((extras.timer(), t_("{} s", extras.timer())))

    def pick(index: int) -> None:
      extras.set_timer(times[index][0])
      window.dismiss()
    window.present(Sheet(N_("Lock doors after"), OptionList([label for _, label in times],
                                                         lambda: next((i for i, (s, _) in enumerate(times) if s == extras.timer()), 0), pick),
                         subtitle=N_("How long after you turn off the car"), on_dismiss=window.dismiss))

  def timer_label() -> str:
    return next((label for s, label in LOCK_TIMES if s == extras.timer()), t_("{} s", extras.timer()))

  rows: list[Widget] = []
  for extra in extras.extras():
    if extra.kind == "timer":
      rows.append(SettingRow(extra.title, extra.line, ValueButton(timer_label, timer_sheet)))
    else:
      rows.append(SettingRow(extra.title, extra.line, Switch(lambda k=extra.key: extras.value(k), flipped(extra))))
  if not rows:
    rows.append(Text(N_("Nothing extra for this car. Everything it supports is on the Vehicle page.")))
  return PanelPage(ListPanel(rows, title=N_("More for your car"), subtitle=N_("Options only some makes and models have")))


class UpstreamCarExtras:
  """CarExtras from StarPilot's vehicle screen: the same conditions on the detected car, the same params and handlers."""

  def __init__(self):
    from openpilot.selfdrive.ui.layouts.settings.starpilot.vehicle import StarPilotVehicleSettingsLayout
    from openpilot.selfdrive.ui.lib.starpilot_state import starpilot_state
    from openpilot.selfdrive.ui.tandem.settings.controllers import confirmed_controller
    self._layout = confirmed_controller(StarPilotVehicleSettingsLayout)()
    self._state = starpilot_state

  def extras(self) -> list[CarExtra]:
    cs, params = self._state.car_state, self._layout._params
    out = [CarExtra("DisableOpenpilotLongitudinal", N_("Use the car's own cruise control"),
                    N_("Turns off openpilot's gas and brake control. openpilot restarts if the car is on."),
                    warn=N_("openpilot stops controlling gas and brakes; the car's adaptive cruise takes over. openpilot restarts if the car is on."))]
    if cs.isGM and (cs.hasPedal or cs.canUsePedal):
      out += [CarExtra("GMPedalLongitudinal", N_("Pedal for gas and brake"), N_("Use the comma pedal for openpilot's speed control")),
              CarExtra("GMDashSpoofOffsets", N_("Offsets on the dash"), N_("Show set-speed offsets on the dashboard"))]
    if cs.isGM and cs.hasOpenpilotLongitudinal:
      out += [CarExtra("IgnoreIgnitionLine", N_("CAN ignition only"), N_("Start only from the car's CAN ignition, not the ignition wire"), "flash"),
              CarExtra("RemoteStartBootsComma", N_("Remote start wakes the device"), N_("Starting the car remotely starts openpilot too"), "flash")]
    if cs.isGM and cs.isVolt and not cs.hasSNG:
      out.append(CarExtra("VoltSNG", N_("Stop and go"), N_("Keep going after a stop on Volts that don't do it themselves")))
    if cs.isJeep:
      out.append(CarExtra("JeepBrakeHold", N_("Brake hold"), N_("Hold after cruise times out at a stop, and go again when traffic moves")))
    if cs.isSubaru:
      out.append(CarExtra("SubaruSNG", N_("Stop and go"), N_("Keep going after a stop")))
      if params.get_bool("SubaruSNG"):
        out.append(CarExtra("SubaruSNGManualParkingBrake", N_("Stop and go with a manual parking brake"), N_("For cars with a hand brake")))
    if cs.isToyota:
      out += [CarExtra("UnlockDoors", N_("Auto-unlock doors"), N_("Unlocks when you shift into park")),
              CarExtra("LockDoorsTimer", N_("Lock doors after"), N_("Locks the doors a while after you turn off the car"), "timer")]
    if cs.isToyota and not cs.hasSNG:
      out.append(CarExtra("SNGHack", N_("Stop and go"), N_("Keep going after a stop on Toyotas that don't do it themselves")))
    if cs.isBolt and cs.hasPedal:
      out.append(CarExtra("RemapCancelToDistance", N_("Use Cancel as a button"), N_("Map the Cancel button like the other steering wheel buttons")))
    if cs.isHKGCanFd and cs.hasOpenpilotLongitudinal:
      out += [CarExtra("HKGRemoteStartBootsComma", N_("EV remote climate wakes the device"), N_("Remote climate starts openpilot too"), "flash"),
              CarExtra("NostalgiaMode", N_("Nostalgia mode"), N_("The left paddle pauses openpilot's gas and brake control"))]
    return out

  def value(self, key: str) -> bool:
    return self._layout._params.get_bool(key)

  def toggle(self, key: str) -> None:
    self._layout.run_confirmed("disable_longitudinal", lambda: self._layout._on_toggle(key))

  def flash(self, key: str) -> None:
    self._layout.run_confirmed("flash_panda", lambda: self._layout._on_panda_firmware_toggle(key, ""))

  def timer(self) -> int:
    return self._layout._params.get_int("LockDoorsTimer")

  def set_timer(self, seconds: int) -> None:
    self._layout._params.put_int("LockDoorsTimer", int(seconds))
