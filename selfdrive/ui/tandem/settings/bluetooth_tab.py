"""Bluetooth: wheel-mounted remotes first, then car audio and nearby devices.

Wheel buttons use StarPilot's wheel controls service: a mapping ties a remote's button to a slot, and controller
slots hold the action. While this screen is open the service runs in test mode, so pressing a button highlights
its row instead of running its action. Pairing and audio go through upstream's BluetoothManager and its dialogs.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Protocol, TYPE_CHECKING

import pyray as rl

from functools import partial
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.base import Component, size_of
from openpilot.selfdrive.ui.tandem.blocks import Label, Stack
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, HeaderControls, Switch
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, grid, inset, place, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, OptionList, SectionHeader, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.model import Rebuilding
from openpilot.selfdrive.ui.tandem.settings.favorites import favorite_action_names
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, tn_
from openpilot.system.ui.lib.application import MousePos

if TYPE_CHECKING:
  from openpilot.starpilot.system.bluetooth.protocol import BluetoothDevice, BluetoothStatus
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

LEARN_SECONDS = 20


class WheelSource(Protocol):
  """What the remote's settings need from StarPilot's wheel-controls daemon: its mappings, learning a button, and test presses."""
  favorite_slots: int
  def mappings(self) -> list[dict]: ...
  def action(self, slot: int) -> str | None: ...                 # action key in a mapping slot
  def actions(self) -> list[tuple[str, str]]: ...                # (key, name) choices, including favorites
  def status(self) -> dict: ...
  def start_learning(self, slot: int) -> None: ...
  def cancel_learning(self) -> None: ...
  def start_testing(self) -> None: ...
  def stop_testing(self) -> None: ...
  def assign(self, mapping_id: str, key: str) -> bool: ...
  def free_slot(self) -> int | None: ...
  def delete(self, mapping_id: str) -> None: ...


class WheelButtons:
  """The Bluetooth remote's buttons as the settings show them: each one's action and whether it's pressed right now."""

  def __init__(self, source: WheelSource):
    self.source = source

  def buttons(self) -> list[dict]:
    return self.source.mappings()

  def action_name(self, mapping: dict) -> str:
    key = self.source.action(mapping["slot"])
    return next((name for k, name in self.source.actions() if k == key), N_("Not set"))

  def pressed(self) -> dict | None:
    status = self.source.status()
    return status.get("last_tested") if status.get("testing") else None

  def is_pressed(self, mapping: dict) -> bool:
    pressed = self.pressed()
    return bool(pressed and pressed.get("mapped") and pressed.get("slot") == mapping["slot"])

  def unassigned_pressed(self) -> bool:
    pressed = self.pressed()
    return bool(pressed and not pressed.get("mapped"))

  def remote_name(self) -> str:
    mappings = self.buttons()
    devices = self.source.status().get("devices") or []
    name = mappings[0]["device_name"] if mappings else (devices[0].get("name") if devices else "")
    return name or N_("No remote connected")

  def start_testing(self) -> None:
    self.source.start_testing()

  def summary(self) -> str:
    count = len(self.buttons())
    return tn_("{} wheel button", "{} wheel buttons", count) if count else N_("No wheel buttons")


# Mock icons for the wheel button actions, by the action key's last part.
ACTION_ICONS = {"engage_openpilot": "play", "disengage_openpilot": "stop", "cycle_driving_personality": "style",
                "toggle_screen_off": "display", "bookmark": "bookmark", "toggle_aol": "wheel", "force_coast": "coast", "set_speed": "gauge"}


def action_icon(key: str) -> str:
  return "star" if key.startswith("favorite:") else ACTION_ICONS.get(key.rsplit(":", 1)[-1], "chevron")


class ActionGrid(Component):
  """The actions as cards in three columns, each with its icon; the chosen one is outlined."""

  def __init__(self, actions: list[tuple[str, str]], selected: Callable[[], int], on_change: Callable[[int], None]):
    super().__init__()
    self._actions = actions
    self._selected = selected
    self._on_change = on_change
    self._pressed: int | None = None

  def _cells(self) -> list[rl.Rectangle]:
    rows = -(-len(self._actions) // 3)
    return grid(self._rect, 3, rows, T.px(10))[:len(self._actions)]

  def _hit(self, pos: MousePos) -> int | None:
    return next((i for i, r in enumerate(self._cells()) if rl.check_collision_point_rec(pos, r)), None)

  def _handle_mouse_press(self, mouse_pos: MousePos) -> None:
    self._pressed = self._hit(mouse_pos)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    super()._handle_mouse_release(mouse_pos)
    hit = self._hit(mouse_pos)
    if hit is not None and hit == self._pressed:
      self._on_change(hit)
    self._pressed = None

  def _render(self, rect: rl.Rectangle) -> None:
    selected = self._selected()
    for i, ((key, name), r) in enumerate(zip(self._actions, self._cells(), strict=True)):
      chosen = i == selected
      draw.fill(r, T.ACCENT_SELECTED if chosen else T.SURFACE_4, T.px(16))
      if chosen:
        draw.stroke(r, T.ACCENT, T.px(16), T.px(2))
      elif self.is_pressed and i == self._pressed:
        draw.pressed(r, T.px(16))
      body = inset(r, x=T.px(14))
      draw.icon(rl.Rectangle(body.x, body.y, T.px(22), body.height), action_icon(key), T.ACCENT_TEXT, T.px(22))
      draw.text(inset(body, left=T.px(34)), name, T.font_px(16), T.TEXT, T.FONT_BOLD if chosen else T.FONT_SEMIBOLD)


class AssignSheet(Component):
  """Step 1: press the button on the remote. Step 2: choose what it does. Save maps it."""
  grow_touch_target = False

  def __init__(self, model: WheelButtons):
    super().__init__()
    self._model = model
    self._slot = model.source.free_slot()
    self._learned: dict | None = None
    self._action = -1
    self._started = False
    self._error = ""
    self._grid = self._child(ActionGrid(model.source.actions(), lambda: self._action, self._pick))

  def _pick(self, index: int) -> None:
    self._action = index

  def show_event(self) -> None:
    super().show_event()
    if self._slot is not None and not self._started:
      self._started = True
      self._model.source.start_learning(self._slot)

  def _update_state(self) -> None:
    learned = self._model.source.status().get("last_learned")
    if learned and learned.get("slot") == self._slot:
      self._learned = learned

  @property
  def ready(self) -> bool:
    return self._learned is not None and self._action >= 0

  def save(self) -> bool:
    if not self.ready or self._learned is None:
      return False
    saved = self._model.source.assign(self._learned["id"], self._model.source.actions()[self._action][0])
    self._error = "" if saved else N_("Remove another button to free an action slot, then try again.")
    return saved

  def cancel(self) -> None:
    self._model.source.cancel_learning()
    if self._learned is not None:
      self._model.source.delete(self._learned["id"])

  def step_one(self) -> tuple[str, str]:
    """The add-button sheet's first step: its title and line, from waiting for a press to the button it heard."""
    if self._error:
      return N_("Couldn't assign this button"), self._error
    if self._slot is None:
      return N_("All button slots are in use"), N_("Remove a button to add another.")
    if self._learned is None:
      remaining = self._model.source.status().get("remaining_seconds")
      return N_("Press the button on your remote"), t_("Listening{}.", t_(" · {} s left", f"{remaining:.0f}") if remaining else "")
    return t_("{} detected", self._learned.get('event_name') or 'Button'), N_("Press a different button on the remote to change it.")

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(330)

  def _render(self, rect: rl.Rectangle) -> None:
    detected = self._learned is not None
    card, right = row(rect, [T.px(280), FILL], T.px(16))
    draw.fill(card, T.SUCCESS_CARD if detected else T.SURFACE_1, T.px(20))
    draw.stroke(card, T.SUCCESS_EDGE if detected else T.TRACK, T.px(20), T.px(1))
    body = inset(card, T.px(20))
    heading, detail = self.step_one()
    cap, well, title, sub, _, note = column(body, [T.px(20), T.px(64), draw.line_height(T.font_px(22)) * 2,
                                                   draw.paragraph_height(detail, T.font_px(15), T.FONT, body.width), FILL,
                                                   draw.line_height(T.SIZE_CAPTION)], T.px(10))
    draw.caption(cap, N_("STEP 1 · PRESS IT"), T.SUCCESS_TEXT if detected else T.ACCENT_TEXT)
    circle = rl.Rectangle(well.x, well.y, T.px(64), T.px(64))
    draw.fill(circle, T.SUCCESS_WELL if detected else T.ACCENT_SURFACE, T.px(32))
    draw.icon(circle, "check" if detected else "locate", T.SUCCESS_TEXT if detected else T.ACCENT_TEXT, T.px(30))
    draw.paragraph(title, heading, T.font_px(22), T.TEXT, T.FONT_EXTRABOLD, spacing=1.0)
    draw.paragraph(sub, detail, T.font_px(15), T.TEXT_TERTIARY)
    draw.text(note, t_("Listening stops after {} s.", LEARN_SECONDS), T.SIZE_CAPTION, T.TEXT_MUTED)

    cap2, grid_rect, foot = column(right, [T.px(20), FILL, draw.line_height(T.SIZE_SUBTITLE)], T.px(10))
    draw.caption(cap2, N_("STEP 2 · CHOOSE WHAT IT DOES"), T.ACCENT_TEXT)
    self._grid.render(grid_rect)
    draw.text(foot, N_("Pulse and glide and driver selfie are in Tuner Mode."), T.SIZE_SUBTITLE, T.TEXT_MUTED)


def wheel_panel(model: WheelButtons, window: SettingsWindow, bt: BluetoothDevices | None = None) -> Component:
  """Connections › Bluetooth Remote: the remote's buttons and their actions, with Add button."""
  def change(mapping: dict) -> Callable[[], None]:
    def show() -> None:
      actions = model.source.actions()
      error = ""

      def pick(index: int) -> None:
        nonlocal error
        if model.source.assign(mapping["id"], actions[index][0]):
          window.dismiss()
        else:
          error = N_("All action slots are in use. Remove another button first.")

      def remove() -> None:
        model.source.delete(mapping["id"])
        window.dismiss()
      current = model.source.action(mapping["slot"])
      window.present(Sheet(mapping.get("event_name") or N_("Button"), OptionList([name for _, name in actions],
                                                                             lambda: next((i for i, (k, _) in enumerate(actions) if k == current), -1),
                                                                             pick, row_height=T.px(52)),
                           subtitle=lambda: error or N_("What this button does while driving"),
                           actions=[Button(N_("Remove"), remove, ButtonStyle.DANGER_SOFT)], on_dismiss=window.dismiss))
    return show

  def add() -> None:
    sheet_body = AssignSheet(model)

    def save() -> None:
      if sheet_body.save():
        window.dismiss()
        model.start_testing()

    def cancel() -> None:
      sheet_body.cancel()
      window.dismiss()
    window.present(Sheet(N_("Assign a button"), sheet_body, actions=[Button(N_("Cancel"), cancel), Button(N_("Save"), save, ButtonStyle.PRIMARY)],
                         on_dismiss=cancel))

  def build() -> ListPanel:
    rows = [WheelRow(i, m, model, change(m)) for i, m in enumerate(model.buttons())]
    add_button = AddButtonRow(model, add)
    if bt is not None:
      for widget in [*rows, add_button]:
        widget.set_enabled(lambda: bt.status().enabled and bt.status().powered)
    return ListPanel([WheelHeader(model, bt), *rows, add_button],
                     footnote=N_("Buttons don't run their actions while this screen is open."))

  return Rebuilding(lambda: tuple((m["id"], m["slot"]) for m in model.buttons()), build)


class WheelHeader(Component):
  """Icon, Bluetooth Remote (not the car's own wheel buttons, under Vehicle) and the remote, with a reminder that pressing
  a button finds it."""
  grow_touch_target = False

  def __init__(self, model: WheelButtons, bt: BluetoothDevices | None = None):
    super().__init__()
    self._model = model
    self._bt = bt
    self._power = self._child(bluetooth_switch(bt)) if bt is not None else None

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(76)

  def set_touch_valid_callback(self, callback: Callable[[], bool]) -> None:
    super().set_touch_valid_callback(callback)
    if self._power is not None:
      self._power.set_touch_valid_callback(callback)

  def set_parent_rect(self, rect: rl.Rectangle) -> None:
    super().set_parent_rect(rect)
    if self._power is not None:
      self._power.set_parent_rect(rect)

  def _render(self, rect: rl.Rectangle) -> None:
    body = inset(rect, left=T.px(20), right=T.px(14))
    well = place(body, T.px(48), T.px(48), Align.START)
    draw.fill(well, T.ACCENT_SURFACE, T.px(14))
    draw.icon(well, "wheel", T.ACCENT_TEXT, T.px(26))
    if self._power is not None:
      w, h = size_of(self._power, body.width / 2)
      self._power.render(place(body, w, h, Align.END))
      body = inset(body, right=w + T.px(14))
    off = self._bt is not None and bluetooth_off(self._bt)
    hint = N_("Press any button to find it")
    chip_w = draw.text_width(hint, T.SIZE_SUBTITLE, T.FONT_SEMIBOLD) + T.px(52)
    if not off and self._model.buttons() and body.width - chip_w >= T.px(210):
      chip = place(body, chip_w, T.px(40), Align.END)
      draw.fill(chip, T.ACCENT_SURFACE, T.px(12))
      draw.icon(rl.Rectangle(chip.x + T.px(12), chip.y, T.px(16), chip.height), "locate", T.ACCENT_TEXT, T.px(16))
      draw.text(inset(chip, left=T.px(38)), hint, T.SIZE_SUBTITLE, T.ACCENT_CHIP_TEXT, T.FONT_SEMIBOLD)
      body = inset(body, right=chip_w + T.px(14))
    text = inset(body, left=T.px(62))
    lines = [draw.line_height(T.font_px(20)), draw.line_height(T.SIZE_SUBTITLE)]
    title, line = column(place(text, text.width, sum(lines) + T.px(2)), lines, T.px(2))
    draw.text(title, N_("Bluetooth Remote"), T.font_px(20), T.TEXT, T.FONT_BOLD)
    detail = N_("Bluetooth is off") if off else self._model.remote_name()
    color = T.SUCCESS_TEXT if not off and self._model.buttons() else T.TEXT_TERTIARY
    draw.text(line, detail, T.SIZE_SUBTITLE, color)


class WheelRow(Component):
  """A "Button N" chip and its action; lit up while that button is pressed."""

  def __init__(self, index: int, mapping: dict, model: WheelButtons, on_click: Callable[[], None]):
    super().__init__()
    self._index, self._mapping, self._model = index, mapping, model
    self.set_click_callback(on_click)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(60)

  def _render(self, rect: rl.Rectangle) -> None:
    pressed = self.enabled and self._model.is_pressed(self._mapping)
    if pressed:
      draw.fill(rect, T.ACCENT_SELECTED)
      draw.stroke(rect, T.ACCENT, 0, T.px(2))
    elif self.is_pressed:
      draw.pressed(rect)
    body = inset(rect, left=T.px(20), right=T.px(12))
    label = t_("Button {}", self._index + 1)
    chip = place(body, draw.text_width(label, T.SIZE_SUBTITLE, T.FONT_EXTRABOLD) + T.px(32), T.px(34), Align.START)
    alpha = 1.0 if self.enabled else T.DISABLED_ALPHA
    draw.fill(chip, draw.alpha(T.ACCENT if pressed else T.CONTROL, alpha), T.px(10))
    draw.text(chip, label, T.SIZE_SUBTITLE, draw.alpha(T.ACCENT_INK if pressed else T.TEXT_SECONDARY, alpha), T.FONT_EXTRABOLD if pressed else T.FONT_BOLD,
              Align.CENTER)
    draw.chevron(rl.Rectangle(body.x + body.width - T.px(18), body.y, T.px(18), body.height), draw.alpha(T.TEXT_TERTIARY, alpha), T.px(18))
    text = inset(body, left=chip.width + T.px(14), right=T.px(30))
    if pressed:
      w = draw.text(text, N_("PRESSED"), T.SIZE_CAPTION, T.ACCENT_TEXT, T.FONT_BOLD, Align.END)
      text = inset(text, right=w + T.px(12))
    draw.text(text, self._model.action_name(self._mapping), T.font_px(18), draw.alpha(T.TEXT, alpha), T.FONT_BOLD if pressed else T.FONT_SEMIBOLD)


class AddButtonRow(Component):
  """+ Add a button, in the accent; says so when an unassigned button was just pressed."""

  def __init__(self, model: WheelButtons, on_click: Callable[[], None]):
    super().__init__()
    self._model = model
    self.set_click_callback(on_click)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(58)

  def _render(self, rect: rl.Rectangle) -> None:
    unassigned = self.enabled and self._model.unassigned_pressed()
    if unassigned:
      draw.fill(rect, T.SUCCESS_CARD)
    if self.is_pressed:
      draw.pressed(rect)
    body = inset(rect, x=T.px(20))
    ink = draw.alpha(T.SUCCESS_TEXT if unassigned else T.ACCENT_TEXT, 1.0 if self.enabled else T.DISABLED_ALPHA)
    draw.icon(rl.Rectangle(body.x, body.y, T.px(20), body.height), "plus", ink, T.px(20))
    label = N_("That button isn't assigned yet. Tap to add it.") if unassigned else N_("Add a button")
    draw.text(inset(body, left=T.px(32)), label, T.font_px(17), ink, T.FONT_BOLD)


class BluetoothDevices(Protocol):
  """What the Bluetooth settings need from StarPilot's Bluetooth manager: devices, pairing, car audio and sound tests."""

  def tick(self) -> None: ...
  def set_active(self, active: bool) -> None: ...
  def status(self) -> BluetoothStatus: ...
  def set_power(self, enabled: bool) -> None: ...
  def power_busy(self) -> bool: ...
  def select(self, address: str) -> bool: ...      # pairs or connects; True when it's connected and its actions should show
  def test_audio(self, address: str) -> None: ...
  def audio_test_text(self) -> str: ...            # the running test's countdown, result or error
  def forget(self, address: str) -> None: ...
  def disconnect(self, address: str) -> None: ...
  def use_for_audio(self, address: str) -> None: ...   # "" stops using any device for openpilot's sounds
  def prompt(self) -> dict | None: ...             # a pairing prompt from the device: id, name, kind, value, display_only
  def respond(self, prompt_id: str, accept: bool, value: str = "") -> None: ...


def bluetooth_off(bt: BluetoothDevices) -> bool:
  status = bt.status()
  return status.available and not status.enabled


def bluetooth_switch(bt: BluetoothDevices) -> HeaderControls:
  power = Switch(lambda: bt.status().enabled, bt.set_power)
  power.set_enabled(lambda: bt.status().available and bt.status().offroad and not bt.power_busy())
  return HeaderControls(Label(N_("Bluetooth"), T.SIZE_SUBTITLE, T.TEXT_SECONDARY, T.FONT_SEMIBOLD, fit=True), power)


def sound_test(bt: BluetoothDevices, address: str, window: SettingsWindow | None) -> None:
  """Upstream's delayed sound test, counted down in our dialog."""
  from openpilot.selfdrive.ui.tandem.overlays import Dialog
  bt.test_audio(address)
  if window is not None:
    window.present(Dialog(N_("Sound test"), bt.audio_test_text, N_("Done"), lambda result: window.dismiss(), cancel_label=None,
                          glyph=lambda r, c, s: draw.icon(r, "volume", c, s)))


def pairing_prompt(bt: BluetoothDevices, prompt: dict, window: SettingsWindow) -> None:
  """A device's pairing request in our dialogs (upstream showed its own): a code to confirm, a PIN or passkey to type,
  or a code to read off this screen."""
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.selfdrive.ui.tandem.overlays import Dialog
  prompt_id = str(prompt.get("id", ""))
  name = str(prompt.get("name") or N_("Bluetooth device"))
  kind, value = str(prompt.get("kind") or ""), str(prompt.get("value") or "")
  glyph = lambda r, c, s: draw.icon(r, "bluetooth", c, s)  # noqa: E731
  if prompt.get("display_only"):
    window.present(Dialog(t_("Pairing with {}", name), value or N_("Follow the steps on the device."), "OK", lambda _: window.dismiss(),
                          cancel_label=None, glyph=glyph))
  elif kind in ("pin", "passkey"):
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.selfdrive.ui.tandem.keyboard import EssentialsKeyboard
    keyboard = EssentialsKeyboard(max_text_size=32, min_text_size=1, action=N_("Pair"))
    keyboard.set_title(t_("Enter the {} for {}", kind, name), N_("It's shown on the device, or in its manual"))
    keyboard.set_callback(lambda result: bt.respond(prompt_id, result == DialogResult.CONFIRM,
                                                     keyboard.text if result == DialogResult.CONFIRM else ""))
    gui_app.push_widget(keyboard)
  else:
    def done(result: DialogResult) -> None:
      window.dismiss()
      bt.respond(prompt_id, result == DialogResult.CONFIRM)
    message = t_("Check that the device shows {}.", value) if value else N_("The device is asking to pair.")
    window.present(Dialog(t_("Pair with {}?", name), message, N_("Pair"), done, glyph=glyph))


def device_sheet(bt: BluetoothDevices, device: BluetoothDevice, window: SettingsWindow) -> Sheet:
  """A connected device's actions (upstream showed its option list): car audio, a sound test, disconnect and forget."""
  from openpilot.selfdrive.ui.tandem.controls import Switch
  from openpilot.selfdrive.ui.tandem.settings.device_sections import confirm

  def disconnect(address: str) -> None:
    bt.disconnect(address)
    window.dismiss()

  offroad = lambda: bt.status().offroad  # noqa: E731
  selected = lambda: bt.status().selected_audio.upper() == device.address.upper()  # noqa: E731
  rows: list[Widget] = []
  if device.audio:
    audio = Switch(selected, lambda on: bt.use_for_audio(device.address if on else ""))
    audio.set_enabled(offroad)
    test = Button(N_("Test"), lambda: sound_test(bt, device.address, window))
    test.set_enabled(offroad)
    rows += [SettingRow(N_("Alerts and Chimes"), N_("Play openpilot's sounds through this device. Change it with the car off."), audio),
             SettingRow(N_("Sound Test"), N_("Plays a sound through the car after a short countdown"), test)]
  forget = Button(N_("Forget"), lambda: confirm(window, t_("Forget {}?", device.name), N_("You'll need to pair it again to use it."), N_("Forget"),
                                            lambda: bt.forget(device.address)), ButtonStyle.DANGER_SOFT)
  forget.set_enabled(offroad)
  rows += [SettingRow(N_("Disconnect"), N_("It reconnects the next time you choose it"), Button(N_("Disconnect"), partial(disconnect, device.address))),
           SettingRow(N_("Forget"), N_("Removes the pairing. Change it with the car off."), forget)]
  return Sheet(device.name, ListPanel(rows, header_divider=False), subtitle=N_("Connected"),
               actions=[Button(N_("Done"), window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss)


def devices_panel(bt: BluetoothDevices, window: SettingsWindow | None = None) -> Component:
  """Connections › Car Audio & Devices: the paired car audio, then devices nearby to pair or connect."""
  def choose(device: BluetoothDevice) -> None:
    if bt.select(device.address) and window is not None:
      window.present(device_sheet(bt, device, window))

  def audio_row(device: BluetoothDevice) -> SettingRow:
    selected = lambda: bt.status().selected_audio.upper() == device.address.upper()  # noqa: E731
    return SettingRow(device.name, lambda: N_("Plays alerts and chimes") if selected() else (N_("Connected") if device.connected else N_("Paired")),
                      Button(N_("Test sound"), lambda: sound_test(bt, device.address, window)), on_click=lambda: choose(device),
                      chevron=False)

  def nearby_row(device: BluetoothDevice) -> SettingRow:
    action = Button(lambda: N_("Connect") if device.paired else N_("Pair"), lambda: choose(device))
    action.set_enabled(lambda: bt.status().offroad)
    return SettingRow(device.name, lambda: N_("Paired") if device.paired else None, action)

  def build() -> Widget:
    """Car audio on its own card; nearby devices on a card below it, as in the mock."""
    status = bt.status()
    header = SectionHeader(N_("CAR AUDIO"), trailing=bluetooth_switch(bt))
    if bluetooth_off(bt):
      return ListPanel([header, Text(N_("Bluetooth is off"))])
    audio = [d for d in status.devices if d.audio and d.paired]
    nearby = [d for d in status.devices if not (d.audio and d.paired) and not d.controller]
    scanning = Label(lambda: N_("Scanning…") if bt.status().discovering else "", T.SIZE_SUBTITLE, T.ACCENT_TEXT, T.FONT, fit=True)
    audio_rows: list[Widget] = [audio_row(d) for d in audio] or [Text(N_("No car audio paired."))]
    nearby_rows: list[Widget] = [nearby_row(d) for d in nearby] or [Text(N_("No devices found yet."))]
    return Stack([
      ListPanel([header, *audio_rows]),
      ListPanel([SectionHeader(N_("NEARBY"), trailing=scanning, divider=True),
                 *nearby_rows],
                footnote=N_("Pairing waits until you're parked.")),
    ], gap=T.px(14), grow=1)

  def key() -> tuple[tuple[tuple[str, bool, bool], ...], bool, bool]:
    status = bt.status()
    return tuple((d.address, d.paired, d.connected) for d in status.devices), status.discovering, bluetooth_off(bt)

  last_prompt = [""]

  def tick() -> None:
    prompt = bt.prompt()
    prompt_id = str(prompt.get("id", "")) if prompt else ""
    if prompt and prompt_id and prompt_id != last_prompt[0] and window is not None:
      pairing_prompt(bt, prompt, window)
    last_prompt[0] = prompt_id

  return Rebuilding(key, build, tick)


# Action names for the wheel's controller actions, by StarPilot key suffix.
ACTION_NAMES = {"engage_openpilot": N_("Engage"), "disengage_openpilot": N_("Disengage"), "cycle_driving_personality": N_("Change driving style"),
                "toggle_screen_off": N_("Screen off / on"), "bookmark": N_("Save a clip"), "toggle_aol": N_("Always-on steering"), "force_coast": N_("Coast")}


class UpstreamWheel:
  """WheelSource backed by StarPilot's wheel controls service."""

  def __init__(self) -> None:
    from openpilot.common.params import Params
    from openpilot.starpilot.common import controller_actions as ca
    from openpilot.starpilot.system.wheel_controls import wheel_controlsd as wc
    self._wc = wc
    self._ca = ca
    self._params = Params(return_defaults=True)
    self._memory = Params(memory=True)
    self.favorite_slots = wc.FAVORITE_SLOT_COUNT

  def mappings(self) -> list[dict]:
    return self._wc.load_mappings(self._params)

  def _slots(self) -> list[dict]:
    return self._wc.load_controller_action_slots(self._params)

  def action(self, slot: int) -> str | None:
    if slot < self.favorite_slots:
      return f"favorite:{slot}"
    entry = self._slots()[slot - self.favorite_slots]
    return entry.get("key") if entry.get("enabled") else None

  def actions(self) -> list[tuple[str, str]]:
    keys = {str(o["key"]).rsplit(":", 1)[-1]: str(o["key"]) for o in self._ca.CONTROLLER_ACTION_OPTIONS}
    choices = [(keys[suffix], name) for suffix, name in ACTION_NAMES.items() if suffix in keys]
    return choices + [(f"favorite:{i}", name) for i, name in enumerate(favorite_action_names(self._params))]

  def status(self) -> dict:
    return self._wc.public_status(self._params, self._memory)

  def start_learning(self, slot: int) -> None:
    self._wc.start_learning(slot, self._memory, self._params)

  def cancel_learning(self) -> None:
    from openpilot.starpilot.tandem.wheel import cancel_learning
    cancel_learning(self._memory, self._params)

  def start_testing(self) -> None:
    from openpilot.starpilot.tandem.wheel import start_testing
    start_testing(self._memory, self._params)

  def stop_testing(self) -> None:
    self._wc.stop_testing(self._memory)

  def free_slot(self) -> int | None:
    used = {m["slot"] for m in self.mappings()}
    return next((self.favorite_slots + i for i, s in enumerate(self._slots())
                 if self.favorite_slots + i not in used and not s.get("enabled")), None)

  def _release_slot(self, slot: int) -> None:
    if slot >= self.favorite_slots and not any(m["slot"] == slot for m in self.mappings()):
      self._wc.set_controller_action_slot(slot - self.favorite_slots, None, "", self._params)

  def assign(self, mapping_id: str, key: str) -> bool:
    """Gives a button an action.

    Args:
      mapping_id: The button.
      key: The action's key; "favorite:N" points it at favorite slot N.

    Returns:
      False when the button or action isn't known, or no slot is free.
    """
    mappings = self.mappings()
    mapping = next((m for m in mappings if m["id"] == mapping_id), None)
    names = dict(self.actions())
    if mapping is None or key not in names:
      return False
    old_slot = mapping["slot"]
    if key.startswith("favorite:"):
      mapping["slot"] = int(key.split(":")[1])
    else:
      if old_slot < self.favorite_slots or sum(m["slot"] == old_slot for m in mappings) > 1:
        slot = self.free_slot()
        if slot is None:
          return False
        mapping["slot"] = slot
      self._wc.set_controller_action_slot(mapping["slot"] - self.favorite_slots, key, names[key], self._params)
    self._wc.save_mappings(mappings, self._params)
    if mapping["slot"] != old_slot:
      self._release_slot(old_slot)
    return True

  def delete(self, mapping_id: str) -> None:
    mapping = next((m for m in self.mappings() if m["id"] == mapping_id), None)
    if mapping is not None and self._wc.delete_mapping(mapping_id, self._params):
      self._release_slot(mapping["slot"])


class UpstreamBluetooth:
  """BluetoothDevices backed by upstream's manager and its pairing policy; prompts, actions and forget use our dialogs."""

  def __init__(self) -> None:
    from openpilot.system.ui.lib.bluetooth_manager import BluetoothManager
    self._manager = BluetoothManager()
    self._manager.set_active(False)
    self._active = False
    self._scan_requested = False

  def tick(self) -> None:
    """Discover devices only after the radio was enabled and reports powered."""
    if not self._active:
      return
    status = self.status()
    if not status.offroad:
      self._scan_requested = False
      return
    if not status.available or status.error or not status.enabled or not status.powered or self.power_busy():
      return
    if status.discovering:
      self._scan_requested = False
    elif not self._scan_requested and not status.pairing_address:
      self._scan_requested = True
      self._manager.set_scanning(True)   # renew after the daemon's scan window; there is no manual Scan button in our panel

  def prompt(self) -> dict | None:
    return self._manager.status.prompt

  def respond(self, prompt_id: str, accept: bool, value: str = "") -> None:
    self._manager.respond(prompt_id, accept, value)

  def set_active(self, active: bool) -> None:
    """Starts or stops Bluetooth work as the page shows or hides; scanning stops with it."""
    if active == self._active:
      return
    self._active = active
    status = self.status()
    if not active and (self._scan_requested or status.discovering) and status.offroad and not self.power_busy():
      self._manager.set_scanning(False)   # a start may still be queued before the first discovering=True poll
    self._scan_requested = False
    self._manager.set_active(active)
    if active:
      self.tick()

  def set_power(self, enabled: bool) -> None:
    status = self.status()
    if status.available and status.offroad and status.enabled != enabled and not self.power_busy():
      self._scan_requested = False
      self._manager.set_power(enabled)

  def power_busy(self) -> bool:
    return bool(self._manager._power_pending)

  def status(self) -> BluetoothStatus:
    status = self._manager.status
    return replace(status, offroad=True) if not status.offroad and self._parked() else status

  @staticmethod
  def _parked() -> bool:
    from openpilot.selfdrive.ui.ui_state import ui_state
    from openpilot.starpilot.tandem.bluetooth import stationary_park
    return stationary_park(ui_state.sm)

  def select(self, address: str) -> bool:
    """Upstream's pair and connect, under its policy; a connected device gets our actions instead of its option list."""
    from openpilot.system.ui.widgets.bluetooth import device_action_allowed
    status = self.status()
    device = next((d for d in status.devices if d.address.upper() == address.upper()), None)
    operation = self._manager.operation_for(address)
    if not operation and status.pairing_address.upper() == address.upper():
      operation = "pairing"
    if device is None or not device_action_allowed(device, operation, status.offroad):
      return False
    if device.paired and device.connected:
      return True
    (self._manager.connect if device.paired else self._manager.pair)(device.address)
    return False

  def disconnect(self, address: str) -> None:
    self._manager.disconnect(address)

  def use_for_audio(self, address: str) -> None:
    self._manager.select_audio(address)

  def test_audio(self, address: str) -> None:
    self._audio_error = ""
    self._manager.test_audio(address)

  def audio_test_text(self) -> str:
    """What upstream's test dialog says, as one line."""
    if not getattr(self, "_audio_error", ""):
      self._audio_error = self._manager.consume_error()
    if self._audio_error:
      return t_("The test didn't play: {}", self._audio_error)
    phase = self._manager.audio_test_phase()
    if phase == "NOW":
      return N_("Playing now. You should hear it through the car.")
    if phase == "complete":
      return N_("Done. If you didn't hear it, check the car's volume and audio source.")
    if phase == "starting":
      return N_("Getting ready…")
    return t_("A sound plays in {}…", phase)


  def forget(self, address: str) -> None:
    """Our sheet asked first; the service independently checks offroad or verified Park."""
    status = self.status()
    device = next((d for d in status.devices if d.address.upper() == address.upper()), None)
    if device is not None and device.paired and status.offroad:
      self._manager.forget(address)
