"""Upstream settings panels shown inside the Essentials window until native screens replace them.

Panels are created on first show, so screens nobody opens cost nothing at startup.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import pyray as rl

from openpilot.system.ui.widgets import Widget

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.layouts.settings.starpilot.main_panel import StarPilotLayout
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component


class Hosted(Component):
  """Draws an upstream panel on the Essentials background."""
  grow_touch_target = False

  def __init__(self, factory: Callable[[], Widget]):
    super().__init__()
    self._factory = factory
    self._panel: Widget | None = None

  @property
  def panel(self) -> Widget:
    if self._panel is None:
      self._panel = self._factory()
    return self._panel

  def can_go_back(self) -> bool:
    return False

  def go_back(self) -> None:
    pass

  def show_event(self) -> None:
    super().show_event()
    self.panel.show_event()

  def hide_event(self) -> None:
    super().hide_event()
    if self._panel is not None:
      self._panel.hide_event()

  def _render(self, rect: rl.Rectangle) -> None:
    draw.fill(rect, T.BG)
    self.panel.render(rect)


_starpilot: StarPilotLayout | None = None


def starpilot_layout() -> StarPilotLayout:
  """StarPilot's settings hub. One instance, as its breadcrumbs find it through StarPilotLayout.active_instance."""
  global _starpilot
  if _starpilot is None:
    from openpilot.selfdrive.ui.layouts.settings.starpilot.main_panel import StarPilotLayout
    _starpilot = StarPilotLayout()
  return _starpilot


def find_leaf(nodes: list[dict], panel: str) -> dict:
  """The leaf of StarPilot's settings tree for a panel name."""
  for node in nodes:
    if node.get("panel") == panel:
      return node
    if "children" in node:
      try:
        return find_leaf(node["children"], panel)
      except KeyError:
        pass
  raise KeyError(panel)


class StarPilotPage(Hosted):
  """One StarPilot panel (e.g. "SOUNDS"), opened directly instead of through StarPilot's hub.

  StarPilot's own back button and breadcrumbs keep working; when they leave the panel, on_exit
  runs (pop the page), or with no on_exit the panel reopens (it is a section of a sidebar page).
  """

  def __init__(self, panel: str, on_exit: Callable[[], None] | None = None, layout: Callable[[], Widget] = starpilot_layout):
    super().__init__(layout)
    self._panel_key = panel
    self._on_exit = on_exit
    self._depth = 0
    self._opening = False
    self._left = False

  def _star(self) -> StarPilotLayout:
    """The panel, as the StarPilot layout it is (starpilot_layout() or a stand-in with the same calls in tests)."""
    return cast("StarPilotLayout", self.panel)

  def _leaf(self) -> dict:
    return find_leaf(cast("list[dict]", type(self._star()).CATEGORIES), self._panel_key)

  def _on_depth(self, depth: int) -> None:
    self._depth = depth
    if depth == 0 and not self._opening:
      self._left = True

  def _open(self) -> None:
    layout = self._star()
    leaf = self._leaf()
    if layout._selected_leaf is leaf and self._depth > 0:
      return
    self._opening = True
    try:
      layout.reset_to_root()
      layout._open_leaf(leaf)
    finally:
      self._opening = False

  def can_go_back(self) -> bool:
    return self._depth > 1

  def go_back(self) -> None:
    self._star().navigate_back()

  def show_event(self) -> None:
    self._star().set_depth_callback(self._on_depth)
    self._open()
    super().show_event()

  def _update_state(self) -> None:
    # Act on a step out of the panel here rather than inside StarPilot's navigation calls.
    if self._left:
      self._left = False
      if self._on_exit is not None:
        self._on_exit()
      else:
        self._open()
