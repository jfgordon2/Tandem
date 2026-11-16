"""Where Tandem joins StarPilot 7's UI: which layout ui.py builds, and the screens MainLayout puts in it.

Tandem sits on openpilot's original screens (MainLayout), not on StarPilot 7's own UI. On the big UI, ui.py takes
MainLayout's path while any Essentials screen is on. Each screen falls back to openpilot's when its variable is "0"
(TANDEM_HOME, TANDEM_SETTINGS, TANDEM_ONROAD, TANDEM_SIDEBAR). With all four "0", or with StarPilot's own recovery
override (STARPILOT_UI=upstream), Tandem stays out and StarPilot 7 picks its UI as it would without Tandem.

Screens that aren't ported to StarPilot 7 yet (PORTING.md) are openpilot's for now.
"""
from __future__ import annotations

from collections.abc import Mapping
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
  from openpilot.starpilot.ui.startup import UiSelection
  return UiSelection(False, "Tandem's Essentials screens on openpilot's layout")


def _enabled(name: str, environment: Mapping[str, str] = os.environ) -> bool:
  return environment.get("STARPILOT_UI") != "upstream" and environment.get(name, "1") != "0"


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
