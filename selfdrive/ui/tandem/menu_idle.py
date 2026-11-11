"""When the menu times out while driving, close what's open on top of settings too.

Upstream's MainLayout goes back to the driving view when the screen's interaction timeout runs out (ScreenTimeoutOnroad
with screen management, 30 s by default; the same timeout Standby waits on), but that only closes the sidebar and
settings. Anything opened from them (a keyboard, Where to?, the driver camera preview, a dialog) is pushed on gui_app's
stack above MainLayout and would stay. This adds one more callback on that same timeout, so they close together.
No upstream edit: it registers like MainLayout does and pops back to the bottom of the stack.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from openpilot.system.ui.lib.application import GuiApplication


def close_overlays(gui_app: GuiApplication, driving: bool) -> bool:
  """Pop everything above MainLayout (the bottom of the stack) while driving. True when something was closed."""
  stack = getattr(gui_app, "_nav_stack", [])
  if not driving or len(stack) < 2:
    return False
  gui_app.pop_widgets_to(stack[0], instant=True)
  return True


_watching: list[bool] = []


def watch() -> None:
  """Register once, as Essentials' driving view is made."""
  if _watching:
    return
  from openpilot.selfdrive.ui.ui_state import device, ui_state
  from openpilot.system.ui.lib.application import gui_app
  _watching.append(True)
  device.add_interactive_timeout_callback(lambda: close_overlays(gui_app, bool(ui_state.started)))
