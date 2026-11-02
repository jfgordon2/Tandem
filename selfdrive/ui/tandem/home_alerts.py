"""Home's alerts and update views (design/homealerts.html, homeupdate.html).

Upstream's OffroadAlert and UpdateAlert still read the params, count the alerts and own the actions (Snooze update,
Acknowledge excessive actuation, Reboot and update); these views only draw them.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, back_glyph
from openpilot.selfdrive.ui.tandem.layout import FILL, column, inset, place, row
from openpilot.selfdrive.ui.tandem.rows import ListPanel, Text
from openpilot.selfdrive.ui.tandem.i18n import N_, tn_

# Upstream's offroad alerts carry only a sentence; these give the ones we know a short title.
ALERT_TITLES = {
  "Offroad_TemperatureTooHigh": N_("Cooling down"),
  "Offroad_ConnectivityNeededPrompt": N_("Connect soon"),
  "Offroad_ConnectivityNeeded": N_("Needs a connection"),
  "Offroad_UpdateFailed": N_("Update failed"),
  "Offroad_ChestnutNotDetected": N_("Chestnut not found"),
  "Offroad_ChestnutOverheated": N_("Chestnut too hot"),
  "Offroad_ChestnutPcieUnavailable": N_("Chestnut unavailable"),
  "Offroad_ChestnutUncompiled": N_("Chestnut model missing"),
  "Offroad_ChestnutUpdateFailed": N_("Chestnut update failed"),
  "Offroad_ChestnutUsbSlow": N_("Chestnut link is slow"),
  "Offroad_IsTakingSnapshot": N_("Taking snapshots"),
  "Offroad_NeosUpdate": N_("System update downloading"),
  "Offroad_UnregisteredHardware": N_("Not registered"),
  "Offroad_CarUnrecognized": N_("Car not recognized"),
  "Offroad_Recalibration": N_("Device mount changed"),
  "Offroad_DriverMonitoringUncertain": N_("Driver camera can't see well"),
  "Offroad_ExcessiveActuation": N_("Excessive actuation"),
}


@dataclass(frozen=True)
class HomeAlert:
  key: str
  text: str
  high: bool       # upstream's severity > 0

  @property
  def title(self) -> str:
    return ALERT_TITLES.get(self.key, "")


class AlertCard(Component):
  """One alert: red for high severity, amber otherwise, with a warning icon, a title and the sentence."""
  grow_touch_target = False
  PAD, ICON, GAP = T.px(16), T.px(22), T.px(14)

  def __init__(self, alert: HomeAlert):
    super().__init__()
    self.alert = alert

  def _text_width(self, width: float) -> float:
    return width - self.PAD * 2 - self.ICON - self.GAP

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    title = draw.line_height(T.font_px(17)) + T.px(4) if self.alert.title else 0
    body = draw.paragraph_height(self.alert.text, T.font_px(15), T.FONT, self._text_width(max_width), 1.35)
    return max_width, self.PAD * 2 - T.px(2) + title + body + T.px(10)

  def _render(self, rect: rl.Rectangle):
    card = inset(rect, y=T.px(5))
    fill, edge, ink, icon = ((T._hex("2A1519"), T._hex("5A2A31"), T.DANGER_TEXT, T._hex("E5646F")) if self.alert.high
                             else (T.WARNING_BANNER, T._hex("4A3B22"), T.WARNING_TITLE, T.WARNING))
    draw.fill(card, fill, T.px(16))
    draw.stroke(card, edge, T.px(16), T.px(1))
    body = inset(card, self.PAD)
    mark, words = row(body, [self.ICON, FILL], self.GAP)
    draw.icon(rl.Rectangle(mark.x, mark.y, self.ICON, self.ICON), "warning", icon, self.ICON)
    y = words.y
    if self.alert.title:
      draw.text(rl.Rectangle(words.x, y, words.width, draw.line_height(T.font_px(17))), self.alert.title, T.font_px(17), ink, T.FONT_BOLD)
      y += draw.line_height(T.font_px(17)) + T.px(4)
    draw.paragraph(rl.Rectangle(words.x, y, words.width, words.y + words.height - y), self.alert.text, T.font_px(15), T.TEXT_SECONDARY,
                   spacing=1.35)


class Header(Component):
  """Back, then a caption (optional) over a title, or a title over a line."""
  grow_touch_target = False

  def __init__(self, on_back: Callable[[], None], title: Callable[[], str], line: Callable[[], str] = lambda: "",
               caption: Callable[[], str] = lambda: ""):
    super().__init__()
    self._back = self._child(Button(on_click=on_back, style=ButtonStyle.NAV, width=T.px(56), height=T.px(56), radius=T.px(14),
                                    glyph=back_glyph))
    self._title, self._line, self._caption = title, line, caption

  def _render(self, rect: rl.Rectangle):
    back, words = row(rect, [T.px(56), FILL], T.px(14))
    self._back.render(place(back, T.px(56), T.px(56)))
    caption, line = self._caption(), self._line()
    parts = ([draw.line_height(T.SIZE_CAPTION)] if caption else []) + [draw.line_height(T.font_px(26))] + \
            ([draw.line_height(T.font_px(15))] if line else [])
    cells = column(place(words, words.width, sum(parts) + T.px(2) * (len(parts) - 1)), parts, T.px(2))
    if caption:
      draw.caption(cells.pop(0), caption, T.SUCCESS_TEXT)
    draw.text(cells.pop(0), self._title(), T.font_px(26), T.TEXT, T.FONT_EXTRABOLD)
    if line:
      draw.text(cells.pop(0), line, T.font_px(15), T.TEXT_TERTIARY)


class AlertsView(Component):
  """Every active offroad alert, high severity first, with upstream's one action when it offers one."""
  grow_touch_target = False

  def __init__(self, alerts: Callable[[], list[HomeAlert]], on_back: Callable[[], None],
               action: Callable[[], tuple[str, Callable[[], None]] | None]):
    super().__init__()
    self._alerts = alerts
    self._action_of = action
    count = lambda: len(alerts())  # noqa: E731
    self._header = self._child(Header(on_back, lambda: tn_("{} alert", "{} alerts", count()),
                                      lambda: N_("openpilot may not start until these are sorted out")))
    self._action = self._child(Button(lambda: (action() or ("", None))[0], lambda: (action() or ("", lambda: None))[1](),
                                      height=T.px(52), weight=T.FONT_BOLD, padding=T.px(22)))
    self._action.set_visible(lambda: action() is not None)
    self._list: ListPanel | None = None
    self._key: tuple = ()

  def _cards(self) -> ListPanel:
    alerts = self._alerts()
    key = tuple(alerts)
    if self._list is None or key != self._key:
      self._list = self._child(ListPanel([AlertCard(a) for a in alerts], dividers=False, header_divider=False))
      self._key = key
    return self._list

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.SURFACE_2, T.RADIUS_PANEL)
    body = inset(rect, x=T.px(20), y=T.px(18))
    footer_h = T.px(52) if self._action.is_visible else 0
    header, cards, footer = column(body, [T.px(60), FILL, footer_h], T.px(14))
    self._header.render(header)
    self._cards().render(inset(cards, x=-T.px(6)))
    if footer_h:
      w = self._action.preferred_size(footer.width)[0]
      self._action.render(rl.Rectangle(footer.x + footer.width - w, footer.y, w, footer.height))


class UpdateView(Component):
  """An update that's ready: its version, the release notes, and Restart and update."""
  grow_touch_target = False

  def __init__(self, version: Callable[[], str], notes: Callable[[], str], on_back: Callable[[], None], on_restart: Callable[[], None]):
    super().__init__()
    self._notes = notes
    self._header = self._child(Header(on_back, version, caption=lambda: N_("Update ready")))
    self._restart = self._child(Button(N_("Restart and update"), on_restart, ButtonStyle.PRIMARY, height=T.px(56), weight=T.FONT_EXTRABOLD,
                                       padding=T.px(28)))
    self._list: ListPanel | None = None
    self._key = ""

  def _panel(self) -> ListPanel:
    notes = self._notes()
    if self._list is None or notes != self._key:
      items: list[Widget] = [Text(p, T.font_px(16), T.TEXT_SECONDARY, padding=(T.px(18), T.px(3))) for p in notes.split("\n") if p.strip()]
      self._list = self._child(ListPanel(items, dividers=False, header_divider=False, background=T._hex("13161A")))
      self._key = notes
    return self._list

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.SURFACE_2, T.RADIUS_PANEL)
    body = inset(rect, x=T.px(20), y=T.px(18))
    header, notes, footer = column(body, [T.px(60), FILL, T.px(56)], T.px(14))
    self._header.render(header)
    self._panel().render(notes)
    w = self._restart.preferred_size(footer.width)[0]
    note, button = row(footer, [FILL, w], T.px(12))
    draw.text(note, N_("It also installs on its own when you turn off the car."), T.font_px(15), T.TEXT_MUTED)
    self._restart.render(button)
