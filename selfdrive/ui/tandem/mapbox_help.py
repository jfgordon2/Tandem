"""How to add a Mapbox key (design/mapboxkey.html), and whether there is one.

StarPilot's navigation takes two Mapbox keys: the public one (pk., the account's default token) for place search
(Search Box API), and a secret one (sk.) for routes, turn guidance (Directions API) and the speed limits its Mapbox filler
adds. Those work with a token's default public scopes; a token is secret (sk.) once it has any secret scope, so the steps
add the read-only DOWNLOADS:READ. Tandem has no field to type a key: both are pasted in StarPilot's Galaxy web app, under
App Keys (classic menu › Tools, /manage_navigation_keys; newer layout: Navigation & Maps › App Keys).
"""
from __future__ import annotations

from collections.abc import Callable

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row

WHERE = "Settings › Driving › Speed & Steering › Navigation"

STEPS = [
  ("Make a Mapbox account", "At account.mapbox.com. The free tier covers personal driving."),
  ("Get two keys", "Your default public token (pk.) is there already. Create a token, keep its public scopes, and also " +
                   "check DOWNLOADS:READ so it starts with sk."),
  ("Open Galaxy", "On this device: Device › This Device › Remote Access › Set Up, then open its link on your phone."),
  ("Paste both keys", "In Galaxy: Navigation & Maps › App Keys. The public key is for search, the secret one for routes."),
]


def _saved(read: Callable[[str], object], key: str) -> bool:
  value = read(key)
  value = value.decode() if isinstance(value, bytes) else str(value or "")
  return bool(value.strip())


def keys(read: Callable[[str], object]) -> tuple[bool, bool]:
  """(public, secret): StarPilot searches places with the public key and routes with the secret one (routing_configured)."""
  return _saved(read, "MapboxPublicKey"), _saved(read, "MapboxSecretKey")


def status(read: Callable[[str], object]) -> tuple[str, bool]:
  """The Mapbox Key row's line, and whether both keys are there."""
  public, secret = keys(read)
  if public and secret:
    return "Added", True
  if public:
    return "Public key only · routes need the secret key too", False
  if secret:
    return "Secret key only · search needs the public key too", False
  return "Not added · needed for place search and routes", False


class Steps(Component):
  """The four numbered steps, two by two, and the note under them."""
  grow_touch_target = False
  NOTE = "The keys stay on this device. Search and routes work as soon as they're saved."

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(128) * 2 + T.px(12) + T.px(14) + draw.line_height(T.font_px(14))

  def _render(self, rect: rl.Rectangle):
    grid, _, note = column(rect, [T.px(128) * 2 + T.px(12), T.px(14), draw.line_height(T.font_px(14))])
    rows = column(grid, [FILL, FILL], T.px(12))
    cells = [c for r in rows for c in row(r, [FILL, FILL], T.px(12))]
    for i, ((title, line), cell) in enumerate(zip(STEPS, cells, strict=True), 1):
      draw.fill(cell, T._hex("1E2227"), T.px(18))
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


def mapbox_key_sheet(done: Callable[[], None]):
  from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
  from openpilot.selfdrive.ui.tandem.overlays import Sheet
  return Sheet("Add Mapbox keys", Steps(), subtitle="For place search, routes, and speed limits the maps don't have",
               actions=[Button("Done", done, ButtonStyle.PRIMARY)], on_dismiss=done)
