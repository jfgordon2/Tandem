"""The Essentials screens MainLayout creates. Each falls back to upstream's when its variable is "0":
TANDEM_SETTINGS, TANDEM_HOME, TANDEM_ONROAD, TANDEM_SIDEBAR.
"""
import os

from openpilot.system.ui.widgets import Widget


def _enabled(name: str) -> bool:
  return os.getenv(name, "1") != "0"


_settings: list = []   # the Essentials settings window, once MainLayout has made it


def settings_window() -> Widget:
  if not _enabled("TANDEM_SETTINGS"):
    from openpilot.selfdrive.ui.layouts.settings.settings import SettingsLayout
    return SettingsLayout()
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow
  window = SettingsWindow()
  _settings[:] = [window]
  return window


def show_settings_tab(tab: int) -> None:
  """After MainLayout has opened settings, move the Essentials window to a tab (home's Software card opens Software)."""
  if _settings:
    _settings[0].open_at(tab)


def home_layout() -> Widget:
  if not _enabled("TANDEM_HOME"):
    from openpilot.selfdrive.ui.layouts.home import HomeLayout
    return HomeLayout()
  from openpilot.selfdrive.ui.tandem.home import essentials_home
  return essentials_home()


def onroad_view() -> Widget:
  if not _enabled("TANDEM_ONROAD"):
    from openpilot.selfdrive.ui.onroad.starpilot.starpilot_onroad_view import StarPilotOnroadView
    return StarPilotOnroadView()
  from openpilot.selfdrive.ui.tandem.onroad.view import EssentialsOnroadView
  return EssentialsOnroadView()


def developer_sidebar():
  """StarPilot's developer sidebar (Developer View), drawn as our tiles; TANDEM_ONROAD=0 brings back StarPilot's."""
  if not _enabled("TANDEM_ONROAD"):
    from openpilot.selfdrive.ui.onroad.starpilot.developer_sidebar import DeveloperSidebar
    return DeveloperSidebar()
  from openpilot.selfdrive.ui.tandem.onroad.developer import developer_sidebar as essentials_developer_sidebar
  return essentials_developer_sidebar()


def sidebar() -> Widget:
  if not _enabled("TANDEM_SIDEBAR"):
    from openpilot.selfdrive.ui.layouts.sidebar import Sidebar
    return Sidebar()
  from openpilot.selfdrive.ui.tandem.sidebar import essentials_sidebar
  return essentials_sidebar()


def _sidebar_width() -> int:
  if not _enabled("TANDEM_SIDEBAR"):
    from openpilot.selfdrive.ui.layouts.sidebar import SIDEBAR_WIDTH as upstream_width
    return upstream_width
  from openpilot.selfdrive.ui.tandem.sidebar import WIDTH
  return int(WIDTH)


def _developer_width() -> int:
  if not _enabled("TANDEM_ONROAD"):
    from openpilot.selfdrive.ui.layouts.sidebar import SIDEBAR_WIDTH
    return SIDEBAR_WIDTH
  from openpilot.selfdrive.ui.tandem.onroad.developer import WIDTH
  return int(WIDTH)


DEVELOPER_SIDEBAR_WIDTH = _developer_width()   # the Developer View panel on the right
MAIN_SIDEBAR_WIDTH = _sidebar_width()   # the left sidebar; StarPilot's developer sidebar on the right keeps its own width
