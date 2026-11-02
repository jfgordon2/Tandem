"""Network: the Wi-Fi list with the connected network on top, and cellular, hotspot and Save Data beside it.

Everything goes through upstream's WifiManager (scanning, connecting, saved networks, tethering, metered),
so this screen only decides what to show. Tests pass an object with the same methods.
"""
from __future__ import annotations

from collections.abc import Callable

import pyray as rl

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.model import Rebuilding
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

MIN_PASSWORD = 8
OPEN, UNSUPPORTED = 0, 4      # upstream SecurityType values
METERED_YES, METERED_NO = 1, 2


def ask_text(title: str, subtitle: str, current: str, on_done: Callable[[str], None], min_length: int = 0, password: bool = False,
             action: str = N_("Save")) -> None:
  """The Essentials keyboard (upstream's, restyled); it closes itself and reports the result."""
  from openpilot.system.ui.lib.application import gui_app
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.selfdrive.ui.tandem.keyboard import EssentialsKeyboard
  keyboard = EssentialsKeyboard(max_text_size=64, min_text_size=min_length, password_mode=password, show_password_toggle=password,
                                action=action)
  keyboard.set_title(title, subtitle)
  keyboard.set_text(current)
  keyboard.set_callback(lambda result: on_done(keyboard.text) if result == DialogResult.CONFIRM else None)
  gui_app.push_widget(keyboard)


class Network:
  def __init__(self, wifi, store: SettingsStore, ask: Callable = ask_text):
    self.wifi = wifi
    self._store = store
    self._ask = ask
    wifi.add_callbacks(need_auth=self._need_password)

  def tick(self) -> None:
    self.wifi.process_callbacks()

  def networks(self) -> list:
    return [n for n in self.wifi.networks if not n.is_tethering]

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

  def choose(self, network) -> None:
    if network.security_type == UNSUPPORTED or self.wifi.connected_ssid == network.ssid:
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
    def with_name(ssid: str) -> None:
      if ssid:
        self._ask(N_("Enter password"), t_("for \"{}\", or leave empty for an open network", ssid), "",
                  lambda password: self.wifi.connect_to_network(ssid, password, hidden=True), 0, True, N_("Connect"))
    self._ask(N_("Network name"), "", "", with_name, 1, False, N_("Next"))

  # Hotspot and data

  @property
  def hotspot(self) -> bool:
    return self.wifi.is_tethering_active()

  def set_hotspot(self, on: bool) -> None:
    self.wifi.set_tethering_active(on)

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
      self.wifi.set_current_network_metered(METERED_YES if on else METERED_NO)

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
      self._store.write({"GsmApn": apn.strip()})
      self._apply_gsm()
    self._ask(N_("APN"), N_("Leave empty for automatic"), self.apn(), done)

  def _apply_gsm(self) -> None:
    self.wifi.update_gsm_settings(self.roaming, self.apn(), self.save_data)

  def summary(self) -> str:
    return self.wifi.connected_ssid or N_("Not connected")


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

  def _render(self, rect: rl.Rectangle):
    bars = _strength_bars(self._strength())
    center = rl.Vector2(rect.x + rect.width / 2, rect.y + rect.height * 0.85)
    for i in range(3):
      radius = rect.height * (0.3 + 0.25 * i)
      color = T.ACCENT_TEXT if i < bars else T.CONTROL
      rl.draw_ring(center, radius - T.px(2), radius, 225, 315, 16, color)
    rl.draw_circle_v(center, T.px(2.5), T.ACCENT_TEXT if bars else T.CONTROL)


def wifi_panel(model: Network) -> Component:
  def network_row(network) -> SettingRow:
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
    rows = [network_row(n) for n in networks] or [Text(N_("Scanning for networks…"))]
    return ListPanel(rows, title=N_("Wi-Fi"), bottom=SettingRow(N_("Join a hidden network"), None, on_click=model.join_hidden))

  return Rebuilding(lambda: tuple(n.ssid for n in model.networks()), build, model.tick)


def cellular_panel(model: Network, open_advanced: Callable[[], None]) -> ListPanel:
  return ListPanel([
    SettingRow(N_("Hotspot"), N_("Share this device's connection"), Switch(lambda: model.hotspot, model.set_hotspot)),
    SettingRow(N_("Hotspot Password"), N_("For phones joining this device's hotspot"), ValueButton(lambda: N_("Edit"), model.edit_hotspot_password)),
    SettingRow(N_("Save Data"), N_("No large uploads on cellular or phone hotspots"), Switch(lambda: model.save_data, model.set_save_data)),
  ], title=N_("Cellular"), end_divider=True, bottom=SettingRow(N_("Roaming, APN and IP address"), None, on_click=open_advanced))


def advanced_panel(model: Network) -> ListPanel:
  return ListPanel([
    SettingRow(N_("Roaming"), N_("Use cellular data outside your carrier's network"), Switch(lambda: model.roaming, model.set_roaming)),
    SettingRow(N_("APN"), lambda: model.apn() or N_("Automatic"), ValueButton(lambda: N_("Edit"), model.edit_apn)),
    SettingRow(N_("IP Address"), lambda: model.wifi.ipv4_address or N_("Not connected")),
  ], title=N_("Roaming, APN and IP address"))


def upstream_wifi():
  from openpilot.system.ui.lib.wifi_manager import WifiManager
  wifi = WifiManager()
  wifi.set_active(False)
  return wifi
