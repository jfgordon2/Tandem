"""How to add a map key (design/stage5-mapboxkey.html), and which keys StarPilot has.

StarPilot 7's navigation takes one Mapbox key, the account's default public token (pk.), for place search, routes and
offline roads; a Google key is optional, for traffic routes and Google's map. Tandem has no field to type a key: both
are pasted in StarPilot's Galaxy web app, under Navigation › Setup, while parked.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.i18n import N_

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.overlays import Sheet

STEPS = [
  (N_("Make a Mapbox account"), N_("At account.mapbox.com. The free tier covers personal driving.")),
  (N_("Copy the public token"), N_("Under Access tokens, the Default public token, which starts with pk. A secret token isn't needed.")),
  (N_("Open Galaxy"), N_("On this device: Device › This Device › Remote Access › Set Up, then open its link on your phone.")),
  (N_("Paste it while parked"), N_("In Galaxy: Navigation › Setup › Mapbox key. A Google key goes there too.")),
]


def status(mapbox: bool, google: bool) -> tuple[str, bool]:
  """The Map Keys row's line, and whether search and routes can work (the Mapbox key is there).

  Args:
    mapbox: StarPilot has a Mapbox key (hasKey).
    google: StarPilot has a Google key (hasGoogleKey).
  """
  if mapbox:
    return (N_("Mapbox and Google added") if google else N_("Mapbox added · Google optional")), True
  return N_("Not added · needed for place search and routes"), False


class Steps(Component):
  """The four numbered steps, two by two, and the note under them."""
  grow_touch_target = False
  NOTE = N_("The keys stay on this device. Search and routes work as soon as they're saved.")

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(110) * 2 + T.px(12) + T.px(14) + draw.line_height(T.font_px(14))

  def _render(self, rect: rl.Rectangle) -> None:
    grid, _, note = column(rect, [T.px(110) * 2 + T.px(12), T.px(14), draw.line_height(T.font_px(14))])
    rows = column(grid, [FILL, FILL], T.px(12))
    cells = [c for r in rows for c in row(r, [FILL, FILL], T.px(12))]
    for i, ((title, line), cell) in enumerate(zip(STEPS, cells, strict=True), 1):
      draw.fill(cell, T.SURFACE_4, T.px(18))
      body = inset(cell, x=T.px(18), y=T.px(16))
      badge, words = row(body, [T.px(34), FILL], T.px(14))
      dot = rl.Rectangle(badge.x, badge.y, T.px(34), T.px(34))
      draw.fill(dot, T.ACCENT_SURFACE, T.px(17))
      draw.text(dot, str(i), T.font_px(17), T.ACCENT_TEXT, T.FONT_EXTRABOLD, Align.CENTER)
      title_h = draw.line_height(T.font_px(18))
      draw.text(rl.Rectangle(words.x, words.y, words.width, title_h), title, T.font_px(18), T.TEXT, T.FONT_BOLD)
      draw.paragraph(rl.Rectangle(words.x, words.y + title_h + T.px(4), words.width, words.height - title_h - T.px(4)), line,
                     T.font_px(15), T.TEXT_TERTIARY, spacing=1.35)
    draw.text(place(note, note.width, note.height), self.NOTE, T.font_px(14), T.TEXT_MUTED)


def map_key_sheet(done: Callable[[], None]) -> Sheet:
  """The help sheet, closed by Done or a drag down."""
  from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
  from openpilot.selfdrive.ui.tandem.overlays import Sheet
  return Sheet(N_("Add a map key"), Steps(), subtitle=N_("Mapbox finds places and plans routes. Google is optional, for traffic."),
               actions=[Button(N_("Done"), done, ButtonStyle.PRIMARY)], height=T.px(432), on_dismiss=done)
