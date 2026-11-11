"""The settings window: four tabs along the bottom, each with its own stack of pages.

The button left of the tabs closes settings on a tab's first page and steps back everywhere deeper.
"""
from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum
from typing import TYPE_CHECKING

import pyray as rl

from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.chrome import BottomNav
from openpilot.selfdrive.ui.tandem.layout import FILL, column
from openpilot.selfdrive.ui.tandem.settings.device import ThisDevicePanel, UpstreamDevice, pairing_page, regulatory_panel, remote_access_page
from openpilot.selfdrive.ui.tandem.settings.bundles import TUNER_MODE
from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import WheelButtons
from openpilot.selfdrive.ui.tandem.settings import connections
from openpilot.selfdrive.ui.tandem.settings.defaults import apply_essentials
from openpilot.selfdrive.ui.tandem.settings.device_sections import (General, Report, backups_panel, confirm, general_panel,
                                                                    report_panel, storage_panel)
from openpilot.selfdrive.ui.tandem.settings.developer import Developer, DeveloperPage
from openpilot.selfdrive.ui.tandem.settings.model import Models
from openpilot.selfdrive.ui.tandem.settings.ram import ram_panel
from openpilot.selfdrive.ui.tandem.ram import now_percent, shared_log
from openpilot.selfdrive.ui.tandem.settings.network_tab import Network, advanced_panel
from openpilot.selfdrive.ui.tandem.settings.software_tab import Software, SoftwarePage
from openpilot.selfdrive.ui.tandem.settings.driving_tab import driving_hub
from openpilot.selfdrive.ui.tandem.settings.live import Live
from openpilot.selfdrive.ui.tandem.settings.pages import HubPage, PanelPage, Section, SectionPage, can_go_back, go_back
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.i18n import N_

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.maps import MapsSource
  from openpilot.selfdrive.ui.tandem.settings.developer import DeveloperSource
  from openpilot.selfdrive.ui.tandem.settings.display import BootLogoSource
  from openpilot.selfdrive.ui.tandem.settings.software_tab import UpdateActions
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import BluetoothDevices, WheelSource
  from openpilot.selfdrive.ui.tandem.settings.device import Device
  from openpilot.selfdrive.ui.tandem.settings.device_sections import DeviceData
  from openpilot.selfdrive.ui.tandem.settings.vehicle import CarCatalog, CarExtras
  from openpilot.selfdrive.ui.tandem.settings.model import ModelSource
  from openpilot.selfdrive.ui.tandem.ram import RamLog
  from openpilot.starpilot.tandem.wifi import WifiManager


class Tab(IntEnum):
  """The settings tabs, left to right."""
  DRIVING = 0
  DEVICE = 1
  CONNECTIONS = 2
  SOFTWARE = 3


TABS = [N_("Driving"), N_("Device"), N_("Connections"), N_("Software")]
DEVELOPER_SECTION = 5
SECTIONS = {"NETWORK": connections.WIFI, "BLUETOOTH": connections.REMOTE}   # where upstream's Network and Bluetooth panels went

# Upstream PanelType names -> where they live here. Home and the sidebar open TOGGLES; it is part of Driving.
PANEL_TABS = {
  "STARPILOT": Tab.DRIVING,
  "TOGGLES": Tab.DRIVING,
  "DEVICE": Tab.DEVICE,
  "DEVELOPER": Tab.DEVICE,
  "NETWORK": Tab.CONNECTIONS,
  "BLUETOOTH": Tab.CONNECTIONS,
  "SOFTWARE": Tab.SOFTWARE,
}


def _upstream_models(notify: Callable[[str], None] | None = None) -> ModelSource:
  from openpilot.selfdrive.ui.tandem.settings.model import UpstreamModels
  return UpstreamModels(notify)


def _upstream_data() -> DeviceData:
  from openpilot.selfdrive.ui.tandem.settings.device_sections import UpstreamData
  return UpstreamData()


def _upstream_device() -> Device:
  return UpstreamDevice()


def _upstream_wifi() -> WifiManager:
  from openpilot.selfdrive.ui.tandem.settings.network_tab import upstream_wifi
  return upstream_wifi()


def _upstream_wheel() -> WheelSource:
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import UpstreamWheel
  return UpstreamWheel()


def _upstream_bluetooth() -> BluetoothDevices:
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import UpstreamBluetooth
  return UpstreamBluetooth()


def _upstream_updates() -> UpdateActions:
  from openpilot.selfdrive.ui.tandem.settings.software_tab import UpstreamUpdates
  return UpstreamUpdates()


def _upstream_boot_logos() -> BootLogoSource:
  from openpilot.selfdrive.ui.tandem.settings.display import UpstreamBootLogos
  return UpstreamBootLogos()


def _upstream_car_extras() -> CarExtras:
  from openpilot.selfdrive.ui.tandem.settings.vehicle import UpstreamCarExtras
  return UpstreamCarExtras()


def _upstream_developer() -> DeveloperSource:
  from openpilot.selfdrive.ui.tandem.settings.developer import UpstreamDeveloper
  return UpstreamDeveloper()


def _upstream_maps() -> MapsSource:
  from openpilot.selfdrive.ui.tandem.settings.maps import UpstreamMaps
  return UpstreamMaps()


def _upstream_cars() -> CarCatalog:
  from openpilot.selfdrive.ui.tandem.settings.vehicle import UpstreamCars
  return UpstreamCars()


class SettingsWindow(Widget):
  """Tandem's settings window, which MainLayout shows in place of upstream's.

  It keeps a stack of pages per tab, an overlay (a sheet or dialog) above them, and the bottom navigation.
  """

  def __init__(self, store: SettingsStore | None = None, live: Live | None = None,
               model_source: Callable[[], ModelSource] | None = None, car_catalog: Callable[[], CarCatalog] | None = None,
               device_data: Callable[[], DeviceData] | None = None, device: Callable[[], Device] | None = None,
               wifi: Callable[[], WifiManager] | None = None, wheel: Callable[[], WheelSource] | None = None,
               bluetooth: Callable[[], BluetoothDevices] | None = None, updates: Callable[[], UpdateActions] | None = None,
               maps_source: Callable[[], MapsSource] | None = None, boot_logos: Callable[[], BootLogoSource] | None = None,
               developer_source: Callable[[], DeveloperSource] | None = None, car_extras: Callable[[], CarExtras] | None = None,
               ram_log: Callable[[], RamLog] | None = None, ram_now: Callable[[], int] | None = None) -> None:
    """The arguments replace device-backed state and StarPilot data in tests; each defaults to the real one."""
    super().__init__()
    self._store = store
    self._live = live
    self.model_source = model_source or (lambda: _upstream_models(self.notice))
    self.car_catalog = car_catalog or _upstream_cars
    self.device_data = device_data or _upstream_data
    self.device = device or _upstream_device
    self.wifi = wifi or _upstream_wifi
    self.wheel = wheel or _upstream_wheel
    self.bluetooth = bluetooth or _upstream_bluetooth
    self.updates = updates or _upstream_updates
    self.maps_source = maps_source or _upstream_maps
    self.developer_source = developer_source or _upstream_developer
    self.car_extras = car_extras or _upstream_car_extras
    self.boot_logos = boot_logos or _upstream_boot_logos
    self.ram_log = ram_log or shared_log
    self.ram_now = ram_now or now_percent
    self._tab = Tab.DRIVING
    self._roots: list[Callable[[], Widget]] = [self._driving, self._device, self._connections, self._software]
    self._stacks: list[list[Widget]] = [[] for _ in TABS]
    self._shown = False
    self._overlay: Widget | None = None
    self._close_callback: Callable[[], None] | None = None
    self._nav = BottomNav(TABS, lambda: self._tab, self.select_tab, on_leading=self.back,
                          leading=lambda: "back" if self.can_go_back() else "close")

  # Upstream SettingsLayout interface, used by MainLayout

  def set_callbacks(self, on_close: Callable[[], None]) -> None:
    self._close_callback = on_close

  def set_current_panel(self, panel_type: object) -> None:
    """Open settings at an upstream PanelType, starting that tab from its first page."""
    name = getattr(panel_type, "name", str(panel_type))
    tab = PANEL_TABS.get(name, Tab.DRIVING)
    self._unwind(tab)
    root = self._stack(tab)[0]
    if isinstance(root, SectionPage) and name == "DEVELOPER":
      root.select(DEVELOPER_SECTION)
    elif isinstance(root, SectionPage) and name in SECTIONS:
      root.select(SECTIONS[name])
    self.select_tab(tab)

  def show_event(self) -> None:
    super().show_event()
    self._shown = True
    self.top.show_event()

  def hide_event(self) -> None:
    super().hide_event()
    self.dismiss()
    self._shown = False
    self.top.hide_event()

  # Navigation

  @property
  def tab(self) -> Tab:
    return self._tab

  @property
  def store(self) -> SettingsStore:
    if self._store is None:
      self._store = SettingsStore()
    return self._store

  @property
  def live(self) -> Live:
    if self._live is None:
      self._live = Live()
    return self._live

  def _stack(self, tab: int) -> list[Widget]:
    stack = self._stacks[tab]
    if not stack:
      stack.append(self._roots[tab]())
    return stack

  @property
  def top(self) -> Widget:
    return self._stack(self._tab)[-1]

  @property
  def depth(self) -> int:
    return len(self._stack(self._tab))

  def can_go_back(self) -> bool:
    return self.depth > 1 or can_go_back(self.top)

  def select_tab(self, tab: int) -> None:
    """Switches tab, keeping each tab's stack."""
    self.dismiss()
    if tab == self._tab:
      return
    if self._shown:
      self.top.hide_event()
    self._tab = Tab(tab)
    if self._shown:
      self.top.show_event()

  def push(self, page: Widget) -> None:
    if self._shown:
      self.top.hide_event()
    self._stack(self._tab).append(page)
    if self._shown:
      page.show_event()

  def pop(self) -> None:
    stack = self._stack(self._tab)
    if len(stack) < 2:
      return
    page = stack.pop()
    if self._shown:
      page.hide_event()
      self.top.show_event()

  # Overlays: sheets and dialogs drawn over the page. The page gets no input while one is up.

  @property
  def overlay(self) -> Widget | None:
    return self._overlay

  def present(self, overlay: Widget) -> None:
    self.dismiss()
    self._overlay = overlay
    overlay.show_event()

  def dismiss(self, callback: Callable[[], None] | None = None) -> None:
    """Closes the sheet or dialog over the window, if any.

    Unlike upstream's Widget.dismiss, the window itself stays: it is MainLayout's settings layout, not a pushed widget.

    Args:
      callback: Called once the overlay is closed, as upstream's dismiss calls it.
    """
    if self._overlay is not None:
      overlay, self._overlay = self._overlay, None
      overlay.hide_event()
    if callback is not None:
      callback()

  def notice(self, message: str) -> None:
    """A message from StarPilot (e.g. why a model can't download now) in our dialog, where it showed its own alert box."""
    from openpilot.selfdrive.ui.tandem import draw
    from openpilot.selfdrive.ui.tandem.overlays import Dialog
    self.present(Dialog(N_("Driving model"), message, "OK", lambda _: self.dismiss(), cancel_label=None,
                        glyph=lambda r, c, s: draw.icon(r, "model", c, s)))

  def back(self) -> None:
    """Steps back: closes the overlay, then a page's own level, then a page, then settings."""
    if self._overlay is not None:
      self.dismiss()
    elif can_go_back(self.top):
      go_back(self.top)
    elif self.depth > 1:
      self.pop()
    elif self._close_callback is not None:
      self._close_callback()

  def open_at(self, tab: int, page: str | None = None, section: int | None = None) -> None:
    """Opens a place in settings from its first page. Settings search opens results with it.

    Args:
      tab: The tab.
      page: A page the Driving hub opens (its `pages` names).
      section: A section of that page's sidebar.
    """
    self.dismiss()
    self._unwind(tab)
    self.select_tab(tab)
    root = self._stack(tab)[0]
    if page is not None and isinstance(root, HubPage):
      root.pages[page]()
    top = self.top
    if section is not None and isinstance(top, SectionPage):
      top.select(section)

  def _unwind(self, tab: int) -> None:
    stack = self._stack(tab)
    while len(stack) > 1:
      page = stack.pop()
      if self._shown and tab == self._tab:
        page.hide_event()
        if len(stack) == 1:
          stack[0].show_event()

  def _render(self, rect: rl.Rectangle) -> None:
    body, nav = column(rect, [FILL, T.NAV_HEIGHT])
    draw.fill(body, T.BG)
    overlay = self._overlay
    events = gui_app.mouse_events
    held = list(events) if overlay is not None else None
    if held is not None:
      events.clear()
    try:
      self.top.render(body)
      self._nav.render(nav)
    finally:
      if held is not None:
        events[:] = held
    if overlay is not None:
      overlay.render(rect)

  # Tabs

  def _driving(self) -> Widget:
    return driving_hub(self)

  def _this_device(self) -> Widget:
    device = self.device()
    return ThisDevicePanel(device, lambda: self.push(pairing_page(device)), lambda: self.push(remote_access_page(device, self)),
                           lambda title, message, label, action, danger, icon: confirm(self, title, message, label, action, danger, icon),
                           lambda: self.push(PanelPage(regulatory_panel())))

  def _device(self) -> Widget:
    data = self.device_data()
    general = General(self.store, data, self.live)
    ram = self.ram_log()
    report = Report(data, self.store, ram)
    return SectionPage(N_("DEVICE"), [
      Section(N_("This Device"), lambda: self._this_device()),
      Section(N_("General"), lambda: general_panel(general, self)),
      Section(N_("Backups"), lambda: backups_panel(general, self)),
      Section(N_("Storage & Data"), lambda: storage_panel(general, self, Models(self.store, self.model_source()))),
      Section(N_("RAM"), lambda: ram_panel(ram, self.ram_now), visible=lambda: bool(ram.snapshots()), dot=ram.unseen),   # once a drive runs low
      Section(N_("Report a Problem"), lambda: report_panel(report)),
      Section(N_("Developer"), lambda: DeveloperPage(Developer(self.store, self.developer_source()), self),
              visible=lambda: TUNER_MODE.is_on(self.store)),
    ])

  def _connections(self) -> Widget:
    network = Network(self.wifi(), self.store)
    return connections.connections_page(network, lambda: self.push(PanelPage(advanced_panel(network))), WheelButtons(self.wheel()),
                                        self.bluetooth(), self)

  def _software(self) -> Widget:
    model = Software(self.store, self.updates(), lambda: apply_essentials(self.store, self.boot_logos))
    return SoftwarePage(model, lambda title, message, label, action: confirm(self, title, message, label, action, icon="restart"), self)

