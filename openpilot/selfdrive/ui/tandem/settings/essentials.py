"""Mount release’s Device and Software pages on StarPilot 7’s owners."""
from __future__ import annotations

from collections.abc import Callable
from functools import cache

from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.settings.pages import PanelPage, Section
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.system.ui.widgets import Widget

def essentials_settings(on_open_arabesque: Callable[[], None] | None, arabesque_available: Callable[[], bool]) -> SettingsWindow:
  """Build the window with StarPilot 7's owners.

  Args:
    on_open_arabesque: openpilot's Developer panel opens Arabesque through MainLayout with this.
    arabesque_available: Whether Arabesque may open now.
  """
  from openpilot.selfdrive.ui.layouts.settings.developer import DeveloperLayout
  from openpilot.selfdrive.ui.layouts.settings.firehose import FirehoseLayout
  from openpilot.selfdrive.ui.layouts.settings.toggles import TogglesLayout
  from openpilot.selfdrive.ui.tandem.prefs import TUNER_MODE
  from openpilot.selfdrive.ui.tandem.ram import shared_log
  from openpilot.selfdrive.ui.tandem.settings.backup_owner import BackupStore
  from openpilot.selfdrive.ui.tandem.settings.backups import backups_panel
  from openpilot.selfdrive.ui.tandem.settings.device import device_page
  from openpilot.selfdrive.ui.tandem.settings.device_owner import DeviceOwner
  from openpilot.selfdrive.ui.tandem.settings.developer import DeveloperPanel
  from openpilot.selfdrive.ui.tandem.settings.general import GeneralPanel
  from openpilot.selfdrive.ui.tandem.settings.general_owner import General
  from openpilot.selfdrive.ui.tandem.settings.ram import ram_section
  from openpilot.selfdrive.ui.tandem.settings.report import Report, report_section
  from openpilot.selfdrive.ui.tandem.settings.storage import StoragePanel
  from openpilot.selfdrive.ui.tandem.settings.storage_owner import StorageOwner
  from openpilot.selfdrive.ui.tandem.settings.software import Software, SoftwarePage
  from openpilot.selfdrive.ui.tandem.software import shared_software
  from openpilot.selfdrive.ui.ui_state import ui_state
  from openpilot.selfdrive.ui.widgets.ssh_key import SshKeyFetcher
  from openpilot.starpilot.galaxy.localization_settings import LocalizationSettingsOwner
  from openpilot.starpilot.tandem.issue_report import send_issue
  from openpilot.starpilot.ui.display_owner import DisplayOwner
  from openpilot.starpilot.ui.slc_offset_feature import native_parked
  from openpilot.system.ui.lib.multilang import multilang

  def ask_password(minimum: int, entered: Callable[[str], None]) -> None:
    """Open the release password keyboard over the device page."""
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.system.ui.widgets import DialogResult
    from openpilot.selfdrive.ui.tandem.keyboard import EssentialsKeyboard
    keyboard = EssentialsKeyboard(min_text_size=minimum, password_mode=True, show_password_toggle=True, action=N_("Set up"))
    keyboard.set_title(N_("Galaxy password"), N_("Use your existing Galaxy password, or set a new one"))

    def done(result: DialogResult) -> None:   # the keyboard closes itself
      text = keyboard.text
      keyboard.clear()
      if result == DialogResult.CONFIRM:
        entered(text)

    keyboard.set_callback(done)
    gui_app.push_widget(keyboard)

  def edit(title: str, current: str, entered: Callable[[str], None]) -> None:
    """Use the release text editor and forward only a confirmed value."""
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.system.ui.widgets import DialogResult
    from openpilot.selfdrive.ui.tandem.keyboard import EssentialsKeyboard

    keyboard = EssentialsKeyboard(action=N_("Save"))
    keyboard.set_title(title, N_("Optional"))
    keyboard.set_text(current)

    def done(result: DialogResult) -> None:
      """The native keyboard has popped itself when this callback runs."""
      if result == DialogResult.CONFIRM and local():
        entered(keyboard.text.strip())
      keyboard.clear()

    keyboard.set_callback(done)
    gui_app.push_widget(keyboard)

  def local() -> bool:
    """Keep preferences distinct from replay and projection."""
    return not ui_state.projection_read_only and ui_state.replay_clock is None

  def parked() -> bool:
    """Use the native device evidence for parked UI actions."""
    return local() and ui_state.is_offroad() and native_parked(ui_state)

  @cache
  def toggles() -> TogglesLayout:
    """Share the native toggle owner with Storage & Data."""
    return TogglesLayout()

  shared_storage: list[StorageOwner] = []

  def storage_owner(offroad: Callable[[], bool] | None = None) -> StorageOwner:
    """One Storage & Data owner, shared with the Driving Model catalog's storage card."""
    if not shared_storage:
      shared_storage.append(StorageOwner(ui_state.params, toggles().request_toggle, local, offroad or parked, lambda: bool(ui_state.engaged)))
    return shared_storage[0]

  def storage() -> Widget:
    """Read and change data through native owners on their appropriate threads."""
    import threading

    from openpilot.starpilot.galaxy.settings import LiveContextSource
    contexts = threading.local()

    def offroad() -> bool:
      """Storage workers use independent transport evidence, never the UI subscriber."""
      if threading.current_thread() is threading.main_thread():
        return parked()
      if not local() or not ui_state.is_offroad():
        return False
      if not hasattr(contexts, "owner"):
        contexts.owner = LiveContextSource(ui_state.params)
      return bool(contexts.owner.offroad())

    return StoragePanel(storage_owner(offroad), window)

  def uninstall() -> None:
    if ui_state.is_offroad() and not ui_state.projection_read_only and ui_state.replay_clock is None:
      ui_state.params.put_bool("DoUninstall", True, block=True)

  def network() -> Widget:
    """Release's Connections: Wi-Fi, cellular and the network test, on Tandem's network services."""
    from openpilot.selfdrive.ui.tandem.settings.connections import connections_page, shared_network_test
    from openpilot.selfdrive.ui.tandem.settings.network_tab import Network, advanced_panel, upstream_wifi
    from openpilot.selfdrive.ui.tandem.settings.network_test import NetworkTestModel
    from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
    model = Network(upstream_wifi(), SettingsStore())
    test = NetworkTestModel(shared_network_test(), lambda: model.wifi.connected_ssid)
    return connections_page(model, lambda: window.push(PanelPage(advanced_panel(model))), window, test)

  owner = DeviceOwner(ui_state, ask_password, lambda message: window.notice(N_("This Device"), message))
  ram = shared_log()

  def general() -> GeneralPanel:
    """Use the native localization and display owners for release’s five rows."""
    model = General(LocalizationSettingsOwner(ui_state.params, local, parked), DisplayOwner(ui_state.params, parked),
                    local, multilang.refresh_language)
    return GeneralPanel(model, window)

  device_sections = [
    Section(N_("General"), general),
    Section(N_("Backups"), lambda: backups_panel(BackupStore(ui_state.params, lambda: local() and ui_state.is_offroad()), window)),
    Section(N_("Storage & Data"), storage),
    ram_section(ram),
    Section(N_("Report a Problem"), lambda: report_section(Report(ram, local, send_issue, edit), window)),
    Section(N_("Developer"), lambda: DeveloperPanel(DeveloperLayout(on_open_arabesque, arabesque_available),
                                                    ui_state.params, SshKeyFetcher(ui_state.params), local, parked, edit), visible=TUNER_MODE.get),
  ]
  def driving() -> Widget:
    """Release's Driving hub on StarPilot 7's settings owners, with its permissions: open settings, parked where it says."""
    from openpilot.selfdrive.ui.tandem.settings.alerts import sound_player
    from openpilot.selfdrive.ui.tandem.settings.driving_tab import DrivingServices, driving_hub
    from openpilot.selfdrive.ui.tandem.settings.live import Live
    from openpilot.selfdrive.ui.tandem.settings.model import StarPilotModels
    from openpilot.selfdrive.ui.tandem.settings.starpilot7 import RoadStyle, StarPilotOwners
    from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
    from openpilot.selfdrive.ui.tandem.settings.vehicle import ToyotaDoors, Vehicle
    from openpilot.starpilot.models.manager import ModelManager
    from openpilot.starpilot.vehicle_selection import VehicleSelectionOwner

    owners = StarPilotOwners(ui_state, lambda: window.shown)
    allowed = owners.configuration_allowed

    def car() -> Vehicle:
      return Vehicle(VehicleSelectionOwner(ui_state.params, lambda: local() and ui_state.is_offroad()), owners.rows,
                     ToyotaDoors(ui_state.params, lambda: ui_state.CP, allowed), lambda: str(getattr(ui_state.CP, "carFingerprint", "") or ""))

    def recount() -> None:
      storage_owner().poll(refresh=True)

    services = DrivingServices(
      SettingsStore(), Live(), owners.rows, RoadStyle(ui_state.params, allowed),
      lambda: StarPilotModels(ModelManager(parked=allowed), lambda message: window.notice(N_("Driving Model"), message)),
      car, owner, lambda: ui_state.CP is not None and not ui_state.CP.pcmCruise, sound_player(allowed),
      lambda: storage_owner().sample.usage, recount)
    return driving_hub(window, services)

  window = SettingsWindow({
    Tab.DRIVING: driving,
    Tab.DEVICE: lambda: device_page(window, owner, device_sections),
    Tab.CONNECTIONS: network,
    Tab.SOFTWARE: lambda: SoftwarePage(Software(shared_software(), ui_state.params.get, uninstall), window),
  }, sections={"DEVELOPER": 6}, auxiliary={"FIREHOSE": lambda: PanelPage(FirehoseLayout())})
  return window
