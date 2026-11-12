"""Connections: what were the Network and Bluetooth tabs, as one tab with four sections (design/connections*.html).

Each section keeps its radio busy only while it's shown, as the two tabs did: Wi-Fi scans while Wi-Fi is open, and Bluetooth
scans, with wheel-button testing, while Bluetooth Remote or Car Audio & Devices is open.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import BluetoothDevices, WheelButtons, devices_panel, wheel_panel
from openpilot.selfdrive.ui.tandem.settings.network_tab import Network, cellular_panel, wifi_panel
from openpilot.selfdrive.ui.tandem.settings.pages import Section, SectionPage
from openpilot.selfdrive.ui.tandem.i18n import N_, tn_

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

WIFI, CELLULAR, REMOTE, AUDIO = range(4)


class WhileShown(Component):
  """A section's panel, with work to start when it shows and stop when it hides."""
  grow_touch_target = False

  def __init__(self, panel: Widget, on_show: Callable[[], None], on_hide: Callable[[], None], on_tick: Callable[[], None] = lambda: None):
    super().__init__()
    self._panel = self._child(panel)
    self._on_show = on_show
    self._on_hide = on_hide
    self._on_tick = on_tick

  def _update_state(self) -> None:
    self._on_tick()

  def show_event(self) -> None:
    self._on_show()
    super().show_event()

  def hide_event(self) -> None:
    super().hide_event()
    self._on_hide()

  def _render(self, rect: rl.Rectangle) -> None:
    self._panel.render(rect)


def buttons_label(count: int) -> str:
  """The remote's button count beside its section, short enough to leave "Bluetooth Remote" whole."""
  return tn_("{} button", "{} buttons", count) if count else ""


def connections_page(network: Network, open_advanced: Callable[[], None], wheel: WheelButtons, bt: BluetoothDevices, window: SettingsWindow) -> SectionPage:
  """The Connections tab: Wi-Fi, cellular, the Bluetooth remote, and car audio, each a section of its sidebar."""
  testing = False

  def bluetooth_tick() -> None:
    nonlocal testing
    bt.tick()
    enabled = bt.status().enabled
    if enabled and not testing:
      wheel.start_testing()
    elif testing and not enabled:
      wheel.source.cancel_learning()
      wheel.source.stop_testing()
    testing = enabled

  def bluetooth_on() -> None:
    bt.set_active(True)
    bluetooth_tick()

  def bluetooth_off() -> None:
    nonlocal testing
    wheel.source.cancel_learning()
    wheel.source.stop_testing()
    testing = False
    bt.set_active(False)

  return SectionPage(N_("CONNECTIONS"), [
    Section(N_("Wi-Fi"), lambda: WhileShown(wifi_panel(network), lambda: network.set_wifi_page(True), lambda: network.set_wifi_page(False)),
            value=network.summary),
    Section(N_("Cellular"), lambda: cellular_panel(network, open_advanced), value=network.cellular_summary),
    Section(N_("Bluetooth Remote"), lambda: WhileShown(wheel_panel(wheel, window, bt), bluetooth_on, bluetooth_off, bluetooth_tick),
            value=lambda: buttons_label(len(wheel.buttons()))),
    Section(N_("Car Audio & Devices"), lambda: WhileShown(devices_panel(bt, window), bluetooth_on, bluetooth_off, bluetooth_tick)),
  ])
