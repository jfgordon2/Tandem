"""Where Tandem joins StarPilot 7's UI: which layout ui.py builds, and the screens MainLayout puts in it.

Tandem sits on openpilot's original screens (MainLayout), not on StarPilot 7's own UI. On the big UI, ui.py takes
MainLayout's path while any Essentials screen is on. Each screen falls back to openpilot's when its variable is "0"
(TANDEM_HOME, TANDEM_SETTINGS, TANDEM_ONROAD, TANDEM_SIDEBAR). With all four "0", or with StarPilot's own recovery
override (STARPILOT_UI=upstream), Tandem stays out and StarPilot 7 picks its UI as it would without Tandem.

Screens that aren't ported to StarPilot 7 yet (PORTING.md) are openpilot's for now.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import os
from typing import TYPE_CHECKING

from openpilot.system.ui.widgets import Widget

if TYPE_CHECKING:
  from openpilot.starpilot.ui.startup import UiSelection

SWITCHES = ("TANDEM_HOME", "TANDEM_SETTINGS", "TANDEM_ONROAD", "TANDEM_SIDEBAR")


def essentials_ui(big_ui: bool, environment: Mapping[str, str] = os.environ) -> bool:
  """Whether ui.py builds MainLayout with Tandem's screens instead of letting StarPilot 7 choose.

  Args:
    big_ui: Whether this is the big UI (comma 3 and 3X). The small UI stays StarPilot's.
    environment: The process environment.
  """
  if not big_ui or environment.get("STARPILOT_UI") == "upstream":
    return False
  return any(environment.get(name, "1") != "0" for name in SWITCHES)


def ui_selection(selection: UiSelection, big_ui: bool, environment: Mapping[str, str] = os.environ) -> UiSelection:
  """StarPilot 7's choice of UI, or openpilot's layout (MainLayout) for Tandem's screens. ui.py logs the reason given."""
  if not essentials_ui(big_ui, environment):
    return selection
  from openpilot.selfdrive.ui.tandem import screenshot
  from openpilot.starpilot.ui.raylib import rl
  from openpilot.starpilot.ui.startup import UiSelection
  screenshot.install(rl, wake=True)   # `touch /tmp/tandem-screenshot` saves the screen (screenshot.py)
  return UiSelection(False, "Tandem's Essentials screens on openpilot's layout")


def _enabled(name: str, environment: Mapping[str, str] = os.environ) -> bool:
  return environment.get("STARPILOT_UI") != "upstream" and environment.get(name, "1") != "0"


_settings: list[Widget] = []   # Tandem's settings window, once MainLayout has made it


def show_settings_tab(tab: int) -> None:
  """After MainLayout has opened settings, move Tandem's window to a tab (Home's Software card opens Software)."""
  if _settings:
    _settings[0].open_at(tab)  # type: ignore[attr-defined]


def home() -> Widget:
  """The parked Home: release's Essentials Home, or openpilot's with TANDEM_HOME=0."""
  if not _enabled("TANDEM_HOME"):
    from openpilot.selfdrive.ui.layouts.home import HomeLayout
    return HomeLayout()
  from openpilot.selfdrive.ui.tandem.home_layout import EssentialsHome
  return EssentialsHome()


def onroad() -> Widget:
  """The driving view: release's Essentials layers over openpilot's camera and model, or openpilot's own view."""
  if not _enabled("TANDEM_ONROAD"):
    from openpilot.selfdrive.ui.onroad.augmented_road_view import AugmentedRoadView
    return AugmentedRoadView()
  from openpilot.selfdrive.ui.tandem.menu_idle import watch
  from openpilot.selfdrive.ui.tandem.onroad.view import EssentialsOnroad
  watch()   # the menu's timeout while driving also closes what's open on top of settings
  return EssentialsOnroad()


def settings(on_open_arabesque: Callable[[], None] | None = None, arabesque_available: Callable[[], bool] = lambda: False) -> Widget:
  """The settings MainLayout shows: release's Essentials window on the big UI, or openpilot's with TANDEM_SETTINGS=0.

  Args:
    on_open_arabesque: Passed on to openpilot's Developer panel, which opens Arabesque through MainLayout.
    arabesque_available: Whether Arabesque may open now.
  """
  from openpilot.system.ui.lib.application import BIG_UI
  if not BIG_UI or not _enabled("TANDEM_SETTINGS"):
    from openpilot.selfdrive.ui.layouts.settings.settings import SettingsLayout
    return SettingsLayout(on_open_arabesque=on_open_arabesque, arabesque_available=arabesque_available)
  from openpilot.selfdrive.ui.tandem.settings.essentials import essentials_settings
  window = essentials_settings(on_open_arabesque, arabesque_available)
  _settings[:] = [window]
  return window


def sidebar() -> Widget:
  """The sidebar beside home and the onroad view: ours, or openpilot's with TANDEM_SIDEBAR=0."""
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


SIDEBAR_WIDTH = _sidebar_width()   # MainLayout's left column, for whichever sidebar it shows
