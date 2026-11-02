"""Back to the driving screen when the menu is left alone while driving.

Upstream's MainLayout already returns to the driving view when the screen's interaction timeout runs out, but with
StarPilot's screen management (on in Essentials) that's ScreenTimeoutOnroad, 30 s by default, and it's also what
Standby's screen-off waits for. So the menu gets its own shorter timer: while driving, MENU_IDLE_S with no touch on
the sidebar, settings, or anything opened from them (a keyboard, Where to?, a dialog) closes them all.

It runs as a gui_app nav-stack tick, every frame whatever is on top, and finds MainLayout at the bottom of the stack,
reading its state rather than adding to it (no upstream edit). README › Branches and merging upstream lists what it reads.
"""
from __future__ import annotations

import time
from collections.abc import Callable

MENU_IDLE_S = 10.0


class MenuIdle:
  def __init__(self, now: Callable[[], float] = time.monotonic):
    self._now = now
    self._last_touch = now()

  def update(self, driving: bool, touched: bool, away: bool) -> bool:
    """One frame. away: something other than the bare driving view is showing. True: go back to it now."""
    now = self._now()
    if touched or not driving or not away:
      self._last_touch = now                 # the timer runs only while driving with the menu up and untouched
      return False
    if now - self._last_touch >= MENU_IDLE_S:
      self._last_touch = now
      return True
    return False


def _main_layout(gui_app):
  stack = getattr(gui_app, "_nav_stack", [])
  return stack[0] if stack else None


def _away(gui_app, main) -> bool:
  sidebar = getattr(main, "_sidebar", None)
  mode = getattr(getattr(main, "_current_mode", None), "name", None)   # MainState.ONROAD, by name: no cereal import here
  return (len(getattr(gui_app, "_nav_stack", [])) > 1 or mode != "ONROAD" or
          bool(sidebar is not None and sidebar.is_visible))


def _back_to_driving(gui_app, main) -> None:
  if len(gui_app._nav_stack) > 1:
    gui_app.pop_widgets_to(main, instant=True)   # a keyboard, Where to? or a dialog opened from the menu
  sidebar = getattr(main, "_sidebar", None)
  if sidebar is not None:
    sidebar.set_visible(False)
  main._set_mode_for_state()                     # upstream's own return: the driving view while started


_watcher: list[MenuIdle] = []


def watch() -> None:
  """Start the timer once, as Essentials' driving view is made."""
  if _watcher:
    return
  from openpilot.system.ui.lib.application import gui_app
  idle = MenuIdle()
  _watcher.append(idle)

  def tick() -> None:
    main = _main_layout(gui_app)
    if main is None or not hasattr(main, "_set_mode_for_state"):
      return
    from openpilot.selfdrive.ui.ui_state import ui_state
    if idle.update(bool(ui_state.started), bool(gui_app.mouse_events), _away(gui_app, main)):
      _back_to_driving(gui_app, main)

  gui_app.add_nav_stack_tick(tick)
