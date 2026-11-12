"""Network: the Wi-Fi list with the connected network on top, and cellular, hotspot and Save Data beside it.

Everything goes through upstream's WifiManager (scanning, connecting, saved networks, tethering, metered),
so this screen only decides what to show. Tests pass an object with the same methods.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TYPE_CHECKING, cast
from collections.abc import Sequence

import pyray as rl

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, HeaderControls, StatusBadge, Switch, Tone, ValueButton
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.model import Rebuilding
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.starpilot.tandem.radios import Radio, RadioControls

if TYPE_CHECKING:
  from openpilot.system.ui.lib.wifi_manager import MeteredType
  from openpilot.system.ui.lib.wifi_manager import Network as WifiNetwork
  from openpilot.starpilot.tandem.cellular import Monitor
  from openpilot.starpilot.tandem.wifi import WifiManager

MIN_PASSWORD = 8
OPEN, UNSUPPORTED = 0, 4      # upstream SecurityType values
METERED_YES, METERED_NO = 1, 2


def ask_text(title: str, subtitle: str, current: str, on_done: Callable[[str], None], min_length: int = 0, password: bool = False,
             action: str = N_("Save"), max_length: int = 64) -> None:
  """The Essentials keyboard (upstream's, restyled); it closes itself and reports the result."""
  from openpilot.system.ui.lib.application import gui_app
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.selfdrive.ui.tandem.keyboard import EssentialsKeyboard
  keyboard = EssentialsKeyboard(max_text_size=max_length, min_text_size=min_length, password_mode=password, show_password_toggle=password,
                                action=action)
  keyboard.set_title(title, subtitle)
  keyboard.set_text(current)
  keyboard.set_callback(lambda result: on_done(keyboard.text) if result == DialogResult.CONFIRM else None)
  gui_app.push_widget(keyboard)


class Network:
  """Connections › Wi-Fi and Cellular: networks, the hotspot, roaming and APN, and Save Data."""

  def __init__(self, wifi: WifiManager, store: SettingsStore, ask: Callable = ask_text, cellular: Monitor | None = None) -> None:
    self.wifi = wifi
    self.radios: RadioControls | None = getattr(wifi, "radios", None)
    self._wifi_page = self._wifi_scanning = False
    self._store = store
    self._ask = ask
    from openpilot.starpilot.tandem.cellular import monitor
    self.cellular = cellular if cellular is not None else getattr(wifi, "cellular_status", None) or monitor()
    wifi.add_callbacks(need_auth=self._need_password)

  def tick(self) -> None:
    self.wifi.process_callbacks()
    if self.radios is not None:
      self.radios.refresh()
    self._sync_wifi_scans()

  def set_wifi_page(self, shown: bool) -> None:
    self._wifi_page = shown
    if shown and self.radios is not None:
      self.radios.refresh()
    self._sync_wifi_scans()

  def _sync_wifi_scans(self) -> None:
    scan = self._wifi_page and self.wifi_enabled
    if scan != self._wifi_scanning:
      self._wifi_scanning = scan
      self.wifi.set_active(scan)

  @property
  def wifi_enabled(self) -> bool:
    if self.radios is None:
      return True
    state = self.radios.state(Radio.WIFI)
    return state.enabled if state is not None else self.radios.read_failed

  def radio_off(self, radio: Radio) -> bool:
    state = self.radios.state(radio) if self.radios is not None else None
    return state is not None and not state.enabled

  def radio_failed(self, radio: Radio) -> bool:
    return self.radios is not None and self.radios.failed == radio

  def radio_switch(self, radio: Radio) -> Switch | None:
    radios = self.radios
    if radios is None:
      return None

    def on() -> bool:
      state = radios.state(radio)
      return state is not None and state.enabled

    def can_toggle() -> bool:
      state = radios.state(radio)
      return state is not None and state.can_toggle and not radios.busy and not radios.read_failed

    control = Switch(on, lambda enabled: radios.set_enabled(radio, enabled))
    control.set_enabled(can_toggle)
    return control

  def networks(self) -> list:
    return [n for n in self.wifi.networks if not n.is_tethering] if self.wifi_enabled else []

  def status(self, ssid: str) -> str:
    if self.wifi.connected_ssid == ssid:
      return N_("Connected")
    if self.wifi.connecting_to_ssid == ssid:
      return N_("Connecting…")
    return N_("Saved") if self.wifi.is_connection_saved(ssid) else ""

  def status_line(self, ssid: str) -> str:
    """The row's line: its status, with the device's local IP address beside Connected (for SSH and the like)."""
    status = self.status(ssid)
    ip = self.wifi.ipv4_address if status == "Connected" else ""
    return f"{status} · {ip}" if ip else status

  def choose(self, network: WifiNetwork) -> None:
    """Connects to a network: at once when it's saved or open, else after asking for its password."""
    if not self.wifi_enabled or network.security_type == UNSUPPORTED or self.wifi.connected_ssid == network.ssid:
      return
    if self.wifi.is_connection_saved(network.ssid):
      self.wifi.activate_connection(network.ssid)
    elif network.security_type == OPEN:
      self.wifi.connect_to_network(network.ssid, "")
    else:
      self._need_password(network.ssid, retry=False)

  def _need_password(self, ssid: str, retry: bool = True) -> None:
    self._ask(N_("Wrong password") if retry else N_("Enter password"), t_("for \"{}\"", ssid), "",
              lambda password: self.wifi.connect_to_network(ssid, password), MIN_PASSWORD, True, N_("Connect"))

  def forget(self, ssid: str) -> None:
    self.wifi.forget_connection(ssid)

  def join_hidden(self) -> None:
    if not self.wifi_enabled:
      return
    def with_name(ssid: str) -> None:
      if ssid:
        self._ask(N_("Enter password"), t_("for \"{}\", or leave empty for an open network", ssid), "",
                  lambda password: self.wifi.connect_to_network(ssid, password, hidden=True), 0, True, N_("Connect"))
    self._ask(N_("Network name"), "", "", with_name, 1, False, N_("Next"))

  # Hotspot and data

  @property
  def hotspot(self) -> bool:
    return self.wifi_enabled and self.wifi.is_tethering_active()

  def set_hotspot(self, on: bool) -> None:
    if not on or self.wifi_enabled:
      self.wifi.set_tethering_active(on)

  def hotspot_name_detail(self) -> str:
    name = self.wifi.tethering_ssid
    return t_("{} · Couldn't save", name) if self.wifi.tethering_name_failed else name

  def edit_hotspot_name(self) -> None:
    """Asks for a new hotspot name, checks it, and saves it."""
    from openpilot.starpilot.tandem.wifi import name_problem

    def ask(current: str, subtitle: str) -> None:
      self._ask(N_("Hotspot name"), subtitle, current, done, 1, False, N_("Save"), max_length=32)

    def done(name: str) -> None:
      problem = name_problem(name)
      error = {"empty": N_("Enter a hotspot name"), "long": N_("Name is too long. Use a shorter name."),
               "control": N_("Use letters, numbers, spaces or punctuation")}.get(problem or "", "")
      if name != self.wifi.tethering_ssid and self.wifi.is_connection_saved(name):
        error = N_("A saved network already uses this name")
      if error:
        ask(name, error)
      else:
        self.wifi.set_tethering_ssid(name)

    ask(self.wifi.tethering_ssid, N_("Connected devices will need to reconnect."))

  def edit_hotspot_password(self) -> None:
    self._ask(N_("Hotspot password"), "", self.wifi.tethering_password, self.wifi.set_tethering_password, MIN_PASSWORD, True)

  @property
  def save_data(self) -> bool:
    return self._store.get_bool("GsmMetered")

  def set_save_data(self, on: bool) -> None:
    """Covers cellular and the current Wi-Fi network, so phone hotspots count as metered too."""
    self._store.write({"GsmMetered": on})
    self._apply_gsm()
    if self.wifi.connected_ssid:
      self.wifi.set_current_network_metered(cast("MeteredType", METERED_YES if on else METERED_NO))

  @property
  def roaming(self) -> bool:
    return self._store.get_bool("GsmRoaming")

  def set_roaming(self, on: bool) -> None:
    self._store.write({"GsmRoaming": on})
    self._apply_gsm()

  def apn(self) -> str:
    return self._store.get_str("GsmApn")

  def edit_apn(self) -> None:
    def done(apn: str) -> None:
      previous, apn = self.apn(), apn.strip()
      self._store.write({"GsmApn": apn})
      self.cellular.apn_saved(apn, previous)
      self._apply_gsm()
    self._ask(N_("APN"), N_("Leave empty for automatic"), self.apn(), done)

  def _apply_gsm(self) -> None:
    self.wifi.update_gsm_settings(self.roaming, self.apn(), self.save_data)

  def summary(self) -> str:
    if self.radio_off(Radio.WIFI):
      return N_("Off")
    return self.wifi.connected_ssid or N_("Not connected")

  def cellular_code(self) -> str:
    if self.radio_failed(Radio.CELLULAR):
      return "radio_failed"
    return "off" if self.radio_off(Radio.CELLULAR) else self.cellular.status().code

  def cellular_label(self) -> str:
    return CELLULAR_LABELS[self.cellular_code()]

  def cellular_summary(self) -> str:
    code = self.cellular_code()
    return "" if code == "checking" else CELLULAR_LABELS[code]

  def cellular_tone(self) -> Tone:
    return CELLULAR_TONES.get(self.cellular_code(), Tone.WARNING)

  def cellular_meta(self, main: bool = False) -> str:
    """The cellular panel's line: the technology and signal, or why there's no service."""
    if self.radio_off(Radio.CELLULAR):
      return N_("Mobile broadband is off")
    status = self.cellular.status()
    if status.code == "checking" or status.observation is None:
      return N_("Reading cellular status")
    if status.code == "no_sim":
      return N_("Cellular data unavailable")
    if status.code == "no_signal" and main:
      return N_("SIM detected · No cellular service")
    value = status.observation
    if status.code == "connected" and value.technology:
      if value.quality is not None:
        strength = SIGNAL_LABELS[min(3, value.quality // 25)]
        return t_("{} · {}", value.technology, strength)
      return str(value.technology)
    if status.code == "connecting" and value.technology:
      return t_("SIM detected · {}", value.technology)
    return N_("SIM detected")

  def cellular_note(self) -> str:
    return CELLULAR_NOTES[self.cellular_code()]

  def cellular_note_color(self) -> rl.Color:
    return {Tone.SUCCESS: T.SUCCESS_TEXT, Tone.ACCENT: T.ACCENT_TEXT, Tone.NEUTRAL: T.TEXT_TERTIARY}.get(
      self.cellular_tone(), T.WARNING)

  def cellular_address(self) -> str:
    if self.radio_off(Radio.CELLULAR):
      return N_("Not connected")
    status = self.cellular.status()
    if status.code == "checking":
      return N_("Checking…")
    if status.code == "connected" and status.observation is not None:
      return status.observation.address or N_("Not available")
    return N_("Not connected")


CELLULAR_LABELS = {"connected": N_("Connected"), "connecting": N_("Connecting…"), "not_connected": N_("Not connected"),
                   "no_sim": N_("No SIM"), "no_signal": N_("No signal"), "wifi": N_("Wi-Fi in use"), "checking": N_("Checking…"),
                   "off": N_("Off"), "radio_failed": N_("Couldn’t change cellular")}
CELLULAR_TONES = {"connected": Tone.SUCCESS, "wifi": Tone.ACCENT, "checking": Tone.NEUTRAL, "off": Tone.NEUTRAL}
CELLULAR_NOTES = {
  "connected": N_("Cellular data is connected."),
  "connecting": N_("APN saved. Waiting for a cellular data connection."),
  "not_connected": N_("Cellular data is not connected. Check your APN, signal and carrier account."),
  "no_sim": N_("No SIM detected. Insert a SIM to use cellular data."),
  "no_signal": N_("SIM detected. No cellular service. Your APN is saved."),
  "wifi": N_("Wi-Fi is connected. Cellular data is not confirmed yet."),
  "checking": N_("Waiting for current modem status."),
  "off": N_("Mobile broadband is off"),
  "radio_failed": N_("Couldn’t change cellular"),
}
SIGNAL_LABELS = [N_("Poor signal"), N_("Moderate signal"), N_("Good signal"), N_("Great signal")]


class CellularPanel(ListPanel):
  """Collect modem state only while this panel is visible, including after APN editing."""

  def __init__(self, model: Network, items: Sequence[Widget], *, main: bool = False, **kwargs: Any) -> None:
    self.model = model
    badge = StatusBadge(model.cellular_label, model.cellular_tone, dot=lambda: model.cellular_code() != "off")
    power = model.radio_switch(Radio.CELLULAR) if main else None
    super().__init__(items, subtitle=lambda: model.cellular_meta(main),
                     header_control=HeaderControls(badge, power) if power else badge, **kwargs)

  def show_event(self) -> None:
    self.model.cellular.set_active(True, self.model.apn())
    super().show_event()

  def hide_event(self) -> None:
    super().hide_event()
    self.model.cellular.set_active(False)

  def _update_state(self) -> None:
    self.model.tick()


def _strength_bars(strength: int) -> int:
  return max(0, min(3, round(strength / 33.0)))


class SignalGlyph(Component):
  """Wi-Fi strength as three arcs; lit ones in the accent."""
  grow_touch_target = False

  def __init__(self, strength: Callable[[], int], secured: bool):
    super().__init__()
    self._strength = strength
    self._secured = secured

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return T.px(28), T.px(28)

  def _render(self, rect: rl.Rectangle) -> None:
    bars = _strength_bars(self._strength())
    center = rl.Vector2(rect.x + rect.width / 2, rect.y + rect.height * 0.85)
    for i in range(3):
      radius = rect.height * (0.3 + 0.25 * i)
      color = T.ACCENT_TEXT if i < bars else T.CONTROL
      rl.draw_ring(center, radius - T.px(2), radius, 225, 315, 16, color)
    rl.draw_circle_v(center, T.px(2.5), T.ACCENT_TEXT if bars else T.CONTROL)


def wifi_panel(model: Network) -> Component:
  """Connections › Wi-Fi: the connected network on top, then the rest, each with Forget."""
  def network_row(network: WifiNetwork) -> SettingRow:
    secured = network.security_type != OPEN
    forget = Button(N_("Forget"), lambda: model.forget(network.ssid), ButtonStyle.GHOST)
    forget.set_visible(lambda: model.wifi.is_connection_saved(network.ssid))
    row_ = SettingRow(network.ssid, lambda: model.status_line(network.ssid) or (N_("Secured") if secured else N_("Open")), forget,
                      on_click=lambda: model.choose(network), leading=SignalGlyph(lambda: network.strength, secured), chevron=False,
                      subtitle_color=lambda: T.SUCCESS_TEXT if model.status(network.ssid) == "Connected" else T.TEXT_TERTIARY)
    row_.set_enabled(network.security_type != UNSUPPORTED)
    return row_

  def build() -> ListPanel:
    networks = model.networks()
    bottom = None
    if model.wifi_enabled:
      rows: list[Widget] = [network_row(n) for n in networks] or [Text(N_("Scanning for networks…"))]
      bottom = SettingRow(N_("Join a hidden network"), None, on_click=model.join_hidden)
    else:
      rows = [Text(N_("Wi-Fi is off") if model.radio_off(Radio.WIFI) else N_("Checking…"))]
    if model.radio_failed(Radio.WIFI):
      rows.insert(0, Text(N_("Couldn’t change Wi-Fi")))
    return ListPanel(rows, title=N_("Wi-Fi"), header_control=model.radio_switch(Radio.WIFI), bottom=bottom)

  return Rebuilding(lambda: (model.wifi_enabled, model.radio_off(Radio.WIFI), model.radio_failed(Radio.WIFI),
                             tuple(n.ssid for n in model.networks())), build, model.tick)


def cellular_panel(model: Network, open_advanced: Callable[[], None]) -> ListPanel:
  """Connections › Cellular: status, roaming, APN and IP address, with Advanced."""
  hotspot = Switch(lambda: model.hotspot, model.set_hotspot)
  hotspot.set_enabled(lambda: model.wifi_enabled and not model.wifi.tethering_name_busy)
  edit_name = ValueButton(lambda: N_("Saving…") if model.wifi.tethering_name_busy else N_("Edit"), model.edit_hotspot_name)
  edit_name.set_enabled(lambda: model.wifi.tethering_name_ready)
  password = ValueButton(lambda: N_("Edit"), model.edit_hotspot_password)
  password.set_enabled(lambda: not model.wifi.tethering_name_busy)
  return CellularPanel(model, [
    SettingRow(N_("Hotspot"), N_("Share this device's connection"), hotspot),
    SettingRow(N_("Hotspot name"), model.hotspot_name_detail, edit_name,
               subtitle_color=lambda: T.DANGER_TEXT if model.wifi.tethering_name_failed else T.ACCENT_TEXT),
    SettingRow(N_("Hotspot Password"), N_("For phones joining this device's hotspot"), password),
    SettingRow(N_("Save Data"), N_("No large uploads on cellular or phone hotspots"), Switch(lambda: model.save_data, model.set_save_data)),
  ], main=True, title=N_("Cellular"), end_divider=True, bottom=SettingRow(N_("Roaming, APN and IP address"), None, on_click=open_advanced))


def advanced_panel(model: Network) -> ListPanel:
  return CellularPanel(model, [
    SettingRow(N_("Roaming"), N_("Use cellular data outside your carrier's network"), Switch(lambda: model.roaming, model.set_roaming)),
    SettingRow(N_("APN"), lambda: model.apn() or N_("Automatic"), ValueButton(lambda: N_("Edit"), model.edit_apn)),
    Text(model.cellular_note, T.font_px(15), model.cellular_note_color),
    SettingRow(N_("Cellular IP address"), model.cellular_address),
  ], title=N_("Roaming, APN and IP address"), footnote=N_("Status updates automatically while this page is open."))


def upstream_wifi() -> WifiManager:
  from openpilot.starpilot.tandem.wifi import WifiManager
  return WifiManager(active=False)
