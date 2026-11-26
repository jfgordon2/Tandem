"""Connections: Wi-Fi, cellular, the Bluetooth remote, Bluetooth devices and the network test, as sections of one tab
(design/connections*.html).

Each section keeps its radio busy only while it's shown: Wi-Fi scans while Wi-Fi is open, Bluetooth searches (and the
remote's buttons are in test mode) while Bluetooth Remote or Bluetooth Devices is open, and a network test stops when
its section is left.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from openpilot.starpilot.ui.raylib import rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.settings.network_tab import Network, cellular_panel, wifi_panel
from openpilot.selfdrive.ui.tandem.settings.network_test import NetworkTestModel, network_test_panel
from openpilot.starpilot.tandem.network_test import NetworkTest
from openpilot.selfdrive.ui.tandem.settings.pages import Section, SectionPage
from openpilot.selfdrive.ui.tandem.i18n import N_, tn_
from openpilot.selfdrive.ui.tandem.settings.android_auto import AndroidAuto, android_auto_panel
from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import BluetoothDevices, WheelButtons, devices_panel, wheel_panel

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

WIFI, CELLULAR, REMOTE, DEVICES, ANDROID_AUTO, TEST = range(6)


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


def shared_network_test() -> NetworkTest:
  """The device's one network tester, shared by every Connections page."""
  from openpilot.starpilot.tandem.network_test import shared
  return shared()


def buttons_label(count: int) -> str:
  """The remote's button count beside its section, short enough to leave "Bluetooth Remote" whole."""
  return tn_("{} button", "{} buttons", count) if count else ""


def connections_page(network: Network, open_advanced: Callable[[], None], window: SettingsWindow, test: NetworkTestModel,
                     wheel: WheelButtons, bt: BluetoothDevices, android_auto: AndroidAuto | None = None) -> SectionPage:
  """The Connections tab: Wi-Fi, cellular, the Bluetooth remote, Bluetooth devices, Android Auto (StarPort) and the network
  test. Without android_auto, Android Auto reads as not available on this device."""
  from openpilot.selfdrive.ui.tandem.settings.android_auto import StarPortStatus
  auto = android_auto or AndroidAuto(StarPortStatus, str)
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
    Section(N_("Bluetooth Devices"), lambda: WhileShown(devices_panel(bt, window), bluetooth_on, bluetooth_off, bluetooth_tick)),
    Section(N_("Android Auto"), lambda: WhileShown(android_auto_panel(auto, window), lambda: bt.set_active(True), lambda: bt.set_active(False),
                                                   bt.tick), value=auto.summary),
    Section(N_("Network Test"), lambda: WhileShown(network_test_panel(test), lambda: None, test.stop), value=test.summary),
  ])
