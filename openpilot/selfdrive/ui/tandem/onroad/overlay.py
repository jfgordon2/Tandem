"""The Essentials layers over the native camera and model, drawn with release's layers (layers.py).

The view (view.py) reads StarPilot 7 and hands each frame over as a DriveDisplay; this only draws it and routes taps.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.layout import inset
from openpilot.selfdrive.ui.tandem.onroad import alerts, extras, layers
from openpilot.selfdrive.ui.tandem.onroad.state import DriveDisplay, LimitDecision, Proposal
from openpilot.starpilot.ui.raylib import rl


def road_rect(rect: rl.Rectangle) -> rl.Rectangle:
  """The camera and overlays sit inside a rounded status border."""
  return inset(rect, T.px(16))


def border_color(state: DriveDisplay) -> rl.Color:
  """Alerts and Help steer color the border; otherwise it's green while engaged."""
  level = state.alert.level if state.alert is not None else None
  if level == alerts.CRITICAL:
    return alerts.CRITICAL_BORDER
  if state.help_steer:
    return layers.LIMIT_BORDER_COLOR
  if level == alerts.WARNING:
    return alerts.WARNING_BORDER
  return T.SUCCESS if state.bar.engaged else T.ONROAD_IDLE_BORDER


class OnroadOverlay(Component):
  """Speed, sign or new-limit card, driver monitor tile, steering arc, chips and the bar, or an alert in their place."""

  grow_touch_target = False

  def __init__(self, state: Callable[[], DriveDisplay], menu: Callable[[], None], speed: Callable[[int], None],
               disengage: Callable[[], None], resolve: Callable[[LimitDecision, bool], None],
               clock: Callable[[], float] = time.monotonic, end_route: Callable[[], None] = lambda: None,
               where_to: Callable[[], None] | None = None):
    super().__init__()
    self._state, self._resolve, self._clock = state, resolve, clock
    self._menu, self._change_speed, self._disengage = menu, speed, disengage
    self._end_route, self._where_to = end_route, where_to
    self._bar = self._new_bar()
    self._bar_context: tuple[bool, bool, bool] | None = None
    self._chips = self._child(layers.StatusChip(lambda: list(self._state().chips)))
    self._arc = self._child(layers.HeadroomArc(lambda: self._state().arc, help_steer=lambda: self._state().help_steer))
    self._help = self._child(layers.HelpSteer())
    self._limit: layers.LimitCard | None = None
    self._decision: LimitDecision | None = None

  def _new_bar(self) -> layers.OnroadBar:
    return self._child(layers.OnroadBar(lambda: self._state().bar, self._menu, self._change_speed, self._disengage, self._end_route,
                                        self._where_to, clock=self._clock))

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
    """A new bar whenever an alert comes or StarPilot's permissions change, so a press started before can't land after."""
    if self._bar_context is not None and self._bar_context != context:
      self._replace_bar()
    self._bar_context = context

  def _limit_card(self, proposal: Proposal | None) -> layers.LimitCard | None:
    """One card per proposal: a new decision needs a new press, and a card only ever answers the decision it showed."""
    identity = proposal.identity if proposal is not None else None
    if identity != self._decision:
      if self._limit is not None:
        self._limit.hide_event()
        self._children.remove(self._limit)
        self._limit = None
      self._decision = identity
      if identity is not None:
        def offer() -> layers.LimitOffer | None:
          current = self._state().proposal
          return current.offer if current is not None and current.identity == identity else None
        self._limit = self._child(layers.LimitCard(offer, lambda: self._resolve(identity, True), lambda: self._resolve(identity, False)))
    return self._limit

  def _render(self, rect: rl.Rectangle) -> None:
    state = self._state()
    attention = state.alert
    bar = state.bar
    self._sync_bar((attention is None and not state.help_steer, bar.can_adjust, bar.can_disengage))
    # A confirmation beside the open menu can overlap the current speed.
    self._limit_card(state.proposal if attention is None and rect.width >= T.px(1000) else None)
    inner = road_rect(rect)
    if attention is not None and attention.level == alerts.CRITICAL:
      alerts.draw_alert(inner, attention.level, attention.title, attention.detail, 1.0)
    else:
      layers.draw_speed(inner, state.speed, state.unit, left=state.left, right=state.right, now=self._clock())
      if state.monitor is not None:
        layers.draw_driver_monitor(layers.dm_tile(inner), 1.0, 0.0 if state.attention_warning else state.monitor, True)
      tile = layers.dm_tile(inner)
      below = tile.y + tile.height + T.px(10)
      if state.pedals is not None:
        below = extras.draw_pedals(tile, state.pedals)
      if state.model is not None:
        extras.draw_model_chip(tile.x + tile.width, below, *state.model)
      if self._limit is not None:
        self._limit.render(inner)
      elif state.posted:
        layers.draw_speed_limit(layers.sign_tile(inner), state.posted, state.vienna)
      if state.turn is not None:
        corner = self._limit is not None or bool(state.posted)
        layers.draw_turn_card(inner, *state.turn, top=layers.turn_below_sign() if corner else layers.turn_card_top())
      if attention is not None:
        alerts.draw_alert(alerts.box(inner, attention.level, attention.title, attention.detail),
                          attention.level, attention.title, attention.detail, 1.0)
      else:
        self._arc.render(inner)
        if state.help_steer:   # a Warning alert drawn by us: like StarPilot's alerts, it takes the bar's place
          self._help.render(inner)
        else:
          self._chips.render(inner)
          self._bar.render(inner)
    draw.stroke(inset(rect, T.px(10)), border_color(state), T.px(18), T.px(6))
    if attention is None or attention.level != alerts.CRITICAL:
      extras.draw_border_halves(rect, inset(rect, T.px(10)), T.px(18), T.px(6), state.border)
