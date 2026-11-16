"""Draw the Essentials overlays over the native camera and model."""
from __future__ import annotations

import time
from collections.abc import Callable

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.layout import inset
from openpilot.selfdrive.ui.tandem.onroad import alerts, hud, size as Z
from openpilot.selfdrive.ui.tandem.onroad.bar import OnroadBar
from openpilot.selfdrive.ui.tandem.onroad.state import Chip, DriveDisplay, LimitDecision, LimitOffer
from openpilot.starpilot.ui.raylib import rl


def road_rect(rect: rl.Rectangle) -> rl.Rectangle:
  """The camera and overlays sit inside a rounded status border."""
  return inset(rect, T.px(16))


class OnroadOverlay(Component):
  """A replayable display for the seven approved driving states."""

  grow_touch_target = False

  def __init__(self, state: Callable[[], DriveDisplay], menu: Callable[[], None], speed: Callable[[int], None],
               disengage: Callable[[], None], resolve: Callable[[LimitDecision, bool], None],
               clock: Callable[[], float] = time.monotonic):
    super().__init__()
    self._state, self._resolve, self._clock = state, resolve, clock
    self._menu, self._change_speed, self._disengage = menu, speed, disengage
    self._bar = self._new_bar()
    self._bar_context: tuple[bool, bool, bool] | None = None
    self._chips = self._child(hud.StatusChip(self._visible_chips))
    self._limit: hud.LimitCard | None = None
    self._decision: LimitDecision | None = None

  def _new_bar(self) -> OnroadBar:
    return self._child(OnroadBar(lambda: self._state().bar, self._menu, self._change_speed, self._disengage))

  def _replace_bar(self) -> None:
    self._bar.hide_event()
    self._children.remove(self._bar)
    self._bar = self._new_bar()

  def reset_controls(self) -> None:
    """Discard pending touches when the driving view is closed."""
    self._limit_card(None)
    self._replace_bar()
    self._bar_context = None

  def _sync_bar(self, context: tuple[bool, bool, bool]) -> None:
    if self._bar_context is not None and self._bar_context != context:
      self._replace_bar()
    self._bar_context = context

  def _visible_chips(self) -> list[tuple[Chip, float]]:
    # In Larger mode the low-priority memory advisory is nearest the bar and
    # the active driving status gets the higher position in the two-chip stack.
    chips = self._state().chips[:2 if Z.larger() else 1]
    return [(chip, 1.0) for chip in reversed(chips)]

  def _limit_card(self, offer: LimitOffer | None) -> hud.LimitCard | None:
    identity = offer.identity if offer is not None else None
    if identity != self._decision:
      if self._limit is not None:
        self._limit.hide_event()
        self._children.remove(self._limit)
        self._limit = None
      self._decision = identity
      if identity is not None:
        self._limit = self._child(hud.LimitCard(lambda: self._state().offer,
                                                 lambda: self._resolve(identity, True),
                                                 lambda: self._resolve(identity, False)))
    return self._limit

  def _render(self, rect: rl.Rectangle) -> None:
    state = self._state()
    attention = state.alert
    self._sync_bar((attention is None, state.bar.adjust_speed, state.bar.disengage))
    # A confirmation beside the open menu can overlap the current speed.
    self._limit_card(state.offer if attention is None and rect.width >= T.px(1000) else None)
    border = (T.DANGER if attention and attention.level == alerts.CRITICAL else
              T.WARNING_BORDER if attention and attention.level == alerts.WARNING else
              T.SUCCESS if state.bar.engaged else T.ONROAD_IDLE_BORDER)
    inner = road_rect(rect)
    if attention is not None and attention.level == alerts.CRITICAL:
      alerts.draw_alert(inner, attention.level, attention.title, attention.detail, 1.0)
    else:
      hud.draw_speed(inner, state.speed, state.unit, left=state.left, right=state.right, now=self._clock())
      if state.monitor is not None:
        hud.draw_driver_monitor(hud.dm_tile(inner), 1.0, 0.0 if state.attention_warning else state.monitor, True)
      if self._limit is not None:
        self._limit.render(inner)
      elif state.posted:
        hud.draw_speed_limit(hud.sign_tile(inner), state.posted, state.vienna)
      if attention is not None:
        alerts.draw_alert(alerts.box(inner, attention.level, attention.title, attention.detail),
                          attention.level, attention.title, attention.detail, 1.0)
      else:
        if state.torque is not None:
          hud.draw_torque(inner, state.torque)
        self._chips.render(inner)
        self._bar.render(inner)
    draw.stroke(inset(rect, T.px(10)), border, T.px(18), T.px(6))
