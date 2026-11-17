"""Connections: Wi-Fi, cellular and the network test, as sections of one tab (design/connections*.html).

Each section keeps its radio busy only while it's shown: Wi-Fi scans while Wi-Fi is open, and a network test stops
when its section is left. Release's Bluetooth Remote and Car Audio & Devices sections come back with StarPilot 7's
controller and Bluetooth owners (PORTING.md).
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
from openpilot.selfdrive.ui.tandem.i18n import N_

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

WIFI, CELLULAR, TEST = range(3)


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


def connections_page(network: Network, open_advanced: Callable[[], None], window: SettingsWindow, test: NetworkTestModel) -> SectionPage:
  """The Connections tab: Wi-Fi, cellular and the network test, each a section of its sidebar."""
  return SectionPage(N_("CONNECTIONS"), [
    Section(N_("Wi-Fi"), lambda: WhileShown(wifi_panel(network), lambda: network.set_wifi_page(True), lambda: network.set_wifi_page(False)),
            value=network.summary),
    Section(N_("Cellular"), lambda: cellular_panel(network, open_advanced), value=network.cellular_summary),
    Section(N_("Network Test"), lambda: WhileShown(network_test_panel(test), lambda: None, test.stop), value=test.summary),
  ])
