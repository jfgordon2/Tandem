"""Presentation for alerts already selected by StarPilot."""
from __future__ import annotations

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.i18n import translate
from openpilot.selfdrive.ui.tandem.layout import Align, inset, place
from openpilot.selfdrive.ui.tandem.onroad import size as Z
from openpilot.starpilot.ui.raylib import rl

INFO, WARNING, CRITICAL = "info", "warning", "critical"
INFO_FILL = draw.alpha(T.SURFACE_3, 0.95)
INFO_INK = T.TEXT_SECONDARY
WARNING_FILL = rl.Color(0x3A, 0x2C, 0x14, 242)
WARNING_TITLE = T.WARNING_TITLE
WARNING_LINE = rl.Color(0xF0, 0xDD, 0xBD, 255)
CRITICAL_FILL = T.CRITICAL_FILL
CRITICAL_LINE = rl.Color(0xF5, 0xC6, 0xCB, 255)

MARGIN_PX = 14
INFO_PAD_PX, INFO_FONT_PX, INFO_ICON_PX = (22, 15), 20, 26
WARNING_PAD_PX, WARNING_TITLE_PX, WARNING_LINE_PX = (24, 14), 26, 17
CRITICAL_ICON_PX, CRITICAL_TITLE_PX, CRITICAL_LINE_PX = 74, 50, 26


def _clean(text: str) -> str:
  return " ".join(translate(text or "").split())   # translate before folding StarPilot's line breaks


def box(rect: rl.Rectangle, alert_level: str, text1: str, text2: str) -> rl.Rectangle:
  """Where an alert draws: the whole road view for a takeover, else a banner along the bottom."""
  if alert_level == CRITICAL:
    return rect
  if alert_level == WARNING:
    lines = draw.line_height(Z.font_px(WARNING_TITLE_PX)) + (Z.px(6) + draw.line_height(Z.font_px(WARNING_LINE_PX)) if _clean(text2) else 0)
    height = Z.px(WARNING_PAD_PX[1]) * 2 + lines
  else:
    height = Z.px(INFO_PAD_PX[1]) * 2 + max(Z.px(INFO_ICON_PX), draw.line_height(Z.font_px(INFO_FONT_PX)))
  return rl.Rectangle(rect.x + Z.px(MARGIN_PX), rect.y + rect.height - Z.px(MARGIN_PX) - height, rect.width - Z.px(MARGIN_PX) * 2, height)


def draw_alert(where: rl.Rectangle, alert_level: str, text1: str, text2: str, opacity: float) -> None:
  """One alert in its box (see box()), faded by opacity as StarPilot's renderer fades alerts in and out."""
  text1, text2 = _clean(text1), _clean(text2)
  fade = lambda color: draw.alpha(color, opacity)  # noqa: E731
  if alert_level == CRITICAL:
    draw.fill(where, fade(CRITICAL_FILL))
    body = inset(where, x=Z.px(48))
    lines = draw.paragraph_lines(text1, Z.font_px(CRITICAL_TITLE_PX), T.FONT_EXTRABOLD, body.width)
    title_h = draw.line_height(Z.font_px(CRITICAL_TITLE_PX)) * 1.1
    line_h = draw.line_height(Z.font_px(CRITICAL_LINE_PX)) if text2 else 0
    total = Z.px(CRITICAL_ICON_PX) + Z.px(16) + title_h * len(lines) + (Z.px(14) + line_h if text2 else 0)
    y = where.y + (where.height - total) / 2
    draw.icon(rl.Rectangle(body.x, y, body.width, Z.px(CRITICAL_ICON_PX)), "wheel", fade(T.TEXT), Z.px(CRITICAL_ICON_PX))
    y += Z.px(CRITICAL_ICON_PX) + Z.px(16)
    for line in lines:
      draw.text(rl.Rectangle(body.x, y, body.width, title_h), line, Z.font_px(CRITICAL_TITLE_PX), fade(T.TEXT), T.FONT_EXTRABOLD, Align.CENTER)
      y += title_h
    if text2:
      draw.text(rl.Rectangle(body.x, y + Z.px(14), body.width, line_h),
                draw.fit(text2, Z.font_px(CRITICAL_LINE_PX), T.FONT, body.width), Z.font_px(CRITICAL_LINE_PX), fade(CRITICAL_LINE), T.FONT, Align.CENTER)
    return
  if alert_level == WARNING:
    draw.fill(where, fade(WARNING_FILL), Z.px(20))
    body = inset(where, x=Z.px(WARNING_PAD_PX[0]), y=Z.px(WARNING_PAD_PX[1]))
    title = rl.Rectangle(body.x, body.y, body.width, draw.line_height(Z.font_px(WARNING_TITLE_PX)))
    draw.text(title, draw.fit(text1, Z.font_px(WARNING_TITLE_PX), T.FONT_EXTRABOLD, body.width), Z.font_px(WARNING_TITLE_PX), fade(WARNING_TITLE),
              T.FONT_EXTRABOLD)
    if text2:
      second = rl.Rectangle(body.x, title.y + title.height + Z.px(6), body.width, draw.line_height(Z.font_px(WARNING_LINE_PX)))
      draw.text(second, draw.fit(text2, Z.font_px(WARNING_LINE_PX), T.FONT, body.width), Z.font_px(WARNING_LINE_PX), fade(WARNING_LINE))
    return
  draw.fill(where, fade(INFO_FILL), Z.px(20))
  body = inset(where, x=Z.px(INFO_PAD_PX[0]), y=Z.px(INFO_PAD_PX[1]))
  draw.icon(place(body, Z.px(INFO_ICON_PX), Z.px(INFO_ICON_PX), Align.START), "info", fade(INFO_INK), Z.px(INFO_ICON_PX))
  words = " · ".join(t for t in (text1, text2) if t)
  text = rl.Rectangle(body.x + Z.px(INFO_ICON_PX) + Z.px(16), body.y, body.width - Z.px(INFO_ICON_PX) - Z.px(16), body.height)
  draw.text(text, draw.fit(words, Z.font_px(INFO_FONT_PX), T.FONT_SEMIBOLD, text.width), Z.font_px(INFO_FONT_PX), fade(T.TEXT), T.FONT_SEMIBOLD)
