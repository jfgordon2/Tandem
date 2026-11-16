"""Essentials parked Home, built from the approved stage 4 mocks."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING
from dataclasses import dataclass, field

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, tn_
from openpilot.selfdrive.ui.tandem.home_software import HomeSoftware

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.forecast import Outlook


@dataclass
class HomeState:
  """What the parked screen's hero card shows: alert count, ignition, the setup line and the version."""
  alerts: int = 0
  ignition: bool = False
  setup: str = ""              # "Standard style · Matching speed limits · Auto lane change"
  software: HomeSoftware = field(default_factory=HomeSoftware)


def readiness(state: HomeState) -> tuple[str, str, rl.Color]:
  """Caption, headline and caption color for the hero card."""
  if state.alerts:
    return N_("NEEDS ATTENTION"), tn_("Check {} alert", "Check {} alerts", state.alerts), T.WARNING
  return N_("READY"), N_("Press cruise to engage") if state.ignition else N_("Start the car to drive"), T.SUCCESS_TEXT


class Hero(Component):
  """Readiness and the current setup; with a forecast (forecast.outlook), the next 12 hours along the bottom
  (design/homeweather.html)."""
  grow_touch_target = False

  def __init__(self, state: Callable[[], HomeState], on_alerts: Callable[[], None], forecast: Callable[[], Outlook | None] = lambda: None):
    super().__init__()
    self._state = state
    self._forecast = forecast
    self.set_click_callback(lambda: on_alerts() if self._state().alerts else None)

  def _render(self, rect: rl.Rectangle) -> None:
    draw.fill(rect, T.SURFACE_2, T.RADIUS_PANEL)
    caption, headline, ink = readiness(self._state())
    outlook = self._forecast()
    body = inset(rect, x=T.px(28))
    lines = [draw.line_height(T.font_px(15)), draw.line_height(T.font_px(40)), draw.line_height(T.font_px(18))]
    if outlook is not None:
      body = inset(rect, left=T.px(28), right=T.px(24), top=T.px(28), bottom=T.px(20))
      top, strip = column(body, [sum(lines) + T.px(20), FILL])
      self._render_outlook(strip, outlook)
      body = top
    cap, title, setup = column(place(body, body.width, sum(lines) + T.px(20)), lines, T.px(10))
    # The mock's status label is a size up from other captions.
    draw.text(cap, caption.upper(), T.font_px(15), ink, T.FONT_BOLD, tracking=T.CAPTION_TRACKING)
    draw.text(title, headline, T.font_px(40), T.TEXT, T.FONT_EXTRABOLD)
    draw.text(setup, self._state().setup, T.font_px(18), T.TEXT_TERTIARY)

  @staticmethod
  def _render_outlook(rect: rl.Rectangle, outlook: Outlook) -> None:
    """The line that matters, when it was updated, then a tile an hour; hours with rain or snow tinted as the chips are."""
    t_size, temp_size, glyph_size = T.font_px(15), T.font_px(21), T.px(26)   # read at a glance from the driver's seat
    tile_h = T.px(10) * 2 + draw.line_height(t_size) + T.px(4) + glyph_size + T.px(4) + draw.line_height(temp_size)
    head_h = T.px(24)
    block = place(rect, rect.width, head_h + T.px(12) + tile_h, v=Align.END)
    head, _, tiles = column(block, [head_h, T.px(12), tile_h])
    ink = T.ACCENT_TEXT if outlook.hazard else T.TEXT_TERTIARY
    icon, words = row(head, [T.px(22), FILL], T.px(10))
    draw.icon(icon, outlook.icon, ink, T.px(22))
    draw.text(words, outlook.summary, T.font_px(18), T.ACCENT_CHIP_TEXT if outlook.hazard else T.TEXT, T.FONT_BOLD)
    draw.text(head, t_("Forecast · updated {}", outlook.updated), T.font_px(13), T.TEXT_MUTED, T.FONT, Align.END)
    for tile, cell in zip(outlook.tiles, row(tiles, [FILL] * len(outlook.tiles), T.px(6)), strict=True):
      draw.fill(cell, T.ACCENT_SURFACE if tile.hazard else T.SURFACE_4, T.px(14))
      inner = inset(cell, y=T.px(10))
      when, _, glyph, _, temp = column(inner, [draw.line_height(t_size), T.px(4), glyph_size, T.px(4), draw.line_height(temp_size)])
      draw.text(when, tile.time, t_size, T.ACCENT_CHIP_TEXT if tile.hazard else T.TEXT_TERTIARY,
                T.FONT_BOLD if tile.hazard else T.FONT_MEDIUM, Align.CENTER)
      draw.icon(glyph, tile.icon, T.ACCENT_TEXT if tile.hazard else T.TEXT_SECONDARY, glyph_size)
      draw.text(temp, f"{tile.temp}°", temp_size, T.TEXT, T.FONT_BOLD, Align.CENTER)


class Card(Component):
  """An icon well, a title and a line; an optional button on the right. The whole card is tappable."""
  grow_touch_target = False

  def __init__(self, glyph_name: str, title: Callable[[], str], line: Callable[[], str], on_click: Callable[[], None] | None,
               button: Button | None = None):
    super().__init__()
    self._glyph = glyph_name
    self._title = title
    self._line = line
    self._button = self._child(button) if button is not None else None
    self.set_click_callback(on_click)

  def _render(self, rect: rl.Rectangle) -> None:
    draw.fill(rect, T.SURFACE_3, T.RADIUS_CARD)
    if self.is_pressed:
      draw.pressed(rect, T.RADIUS_CARD)
    body = inset(rect, x=T.px(20))
    well = place(body, T.ICON_WELL, T.ICON_WELL, Align.START)
    draw.fill(well, T.ACCENT_SURFACE, T.px(16))
    draw.icon(well, self._glyph, T.ACCENT_TEXT, T.px(26))
    body = inset(body, left=T.ICON_WELL + T.px(18))
    if self._button is not None:
      w, h = self._button.preferred_size(body.width / 3)
      self._button.render(place(body, w, h, Align.END))
      body = inset(body, right=w + T.px(14))
    # The line wraps to two lines, as in the mock ("Installs when you turn off / the car").
    line_h = draw.paragraph_height(self._line(), T.font_px(15), T.FONT, body.width, 1.0)
    lines = [draw.line_height(T.font_px(22)), min(line_h, draw.line_height(T.font_px(15)) * 2)]
    title, line = column(place(body, body.width, sum(lines) + T.px(4)), lines, T.px(4))
    draw.text(title, self._title(), T.font_px(22), T.TEXT, T.FONT_BOLD)
    draw.paragraph(line, self._line(), T.font_px(15), T.TEXT_TERTIARY, spacing=1.0, max_lines=2)


class HomeContent(Component):
  """Readiness, optional weather, and the Software or Update ready card."""

  grow_touch_target = False

  def __init__(self, state: Callable[[], HomeState], on_alerts: Callable[[], None],
               on_notes: Callable[[], None], on_software: Callable[[], None], forecast: Callable[[], Outlook | None] = lambda: None):
    super().__init__()
    self._hero = self._child(Hero(state, on_alerts, forecast))
    notes = Button(N_("Notes"), on_notes, font_size=T.font_px(16), height=T.px(48), radius=T.px(12),
                   padding=T.px(16))
    notes.set_visible(lambda: state().software.ready)
    self._update = self._child(Card("download", lambda: software_title(state().software),
                                    lambda: software_line(state().software),
                                    lambda: on_notes() if state().software.ready else on_software(), notes))

  def _render(self, rect: rl.Rectangle) -> None:
    top, bottom = column(rect, [FILL, T.px(92)], T.px(14))
    self._hero.render(top)
    self._update.render(bottom)


def software_title(software: HomeSoftware) -> str:
  return N_("Update ready") if software.ready else N_("Software")


def software_line(software: HomeSoftware) -> str:
  """Only call the installed version current after the updater confirms it."""
  if software.ready:
    return N_("Restart to install")
  if software.current:
    return t_("Up to date · {}", software.installed) if software.installed else N_("Up to date")
  return software.installed


def home_content_rect(rect: rl.Rectangle) -> rl.Rectangle:
  """The card area beside the sidebar in all three parked views."""
  return inset(rect, left=T.px(16), right=T.px(18), top=T.px(18), bottom=T.px(18))
