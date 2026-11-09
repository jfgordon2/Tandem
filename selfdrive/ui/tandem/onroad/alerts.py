"""Onroad alerts in the mock's three levels (design/alertstyles.html): StarPilot still picks the alert, its text, sound
and timing; only the drawing changes.

- Info: a dark pill with an info icon at the bottom; the border keeps its engaged or disengaged color.
- Warning: an amber two-line card at the bottom and an amber border.
- Critical: a full-screen dark red takeover with a steering wheel icon and a red border.

Light Turned Green, Lead Departed, Car Detected in Blindspot (as Lane change blocked), lane changes, turn progress and the
Low Memory notice are left to the status chips;
Speed limit changed is left to the new-limit card while it asks.
"""
from __future__ import annotations

from dataclasses import replace

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.onroad import size as Z
from openpilot.selfdrive.ui.tandem.layout import Align, inset, place
from openpilot.selfdrive.ui.tandem.i18n import translate
from openpilot.selfdrive.ui.tandem.fonts import face_for, font

INFO, WARNING, CRITICAL, REVERSE = "info", "warning", "critical", "reverse"

# cereal's values: SelfdriveState.AlertSize and AlertStatus (StarPilot's status adds starpilot = 3)
SIZE_FULL = 3
STATUS_USER_PROMPT, STATUS_CRITICAL = 1, 2

WARNING_BORDER = T.WARNING_BORDER
CRITICAL_BORDER = rl.Color(0xD9, 0x43, 0x4F, 255)

INFO_FILL = rl.Color(0x1A, 0x1D, 0x22, 242)
INFO_INK = rl.Color(0xC9, 0xD0, 0xDA, 255)
WARNING_FILL = rl.Color(0x3A, 0x2C, 0x14, 242)
WARNING_TITLE = rl.Color(0xFF, 0xD0, 0x8A, 255)
WARNING_LINE = rl.Color(0xF0, 0xDD, 0xBD, 255)
CRITICAL_FILL = rl.Color(0x2A, 0x0E, 0x12, 245)
CRITICAL_LINE = rl.Color(0xF5, 0xC6, 0xCB, 255)

# Sizes in mock px, drawn through onroad/size.py so Larger text (design/onroadlarge-alert.html) grows them too.
MARGIN_PX = 16
INFO_PAD_PX, INFO_FONT_PX, INFO_ICON_PX = (22, 18), 24, 30
WARNING_PAD_PX, WARNING_TITLE_PX, WARNING_LINE_PX = (24, 20), 32, 22
CRITICAL_ICON_PX, CRITICAL_TITLE_PX, CRITICAL_LINE_PX = 84, 44, 24


def level(size: int, status: int, alert_type: str = "") -> str:
  """Which of the mock's levels an alert is. Full-screen or critical alerts take over; prompts warn; the rest inform.
  Reverse gear keeps StarPilot's text-only drawing over the rear view."""
  if size == SIZE_FULL and (alert_type or "").split("/", 1)[0] == "reverseGear":
    return REVERSE
  if size == SIZE_FULL or status == STATUS_CRITICAL:
    return CRITICAL
  if status == STATUS_USER_PROMPT:
    return WARNING
  return INFO


CHIP_ALERTS = {"greenLight", "leadDeparting", "laneChange", "laneChangeBlocked", "laneChangeBlockedLoud", "turningLeft", "turningRight"}
CHIP_ALERT_TYPES = {"lowMemory/permanent"}   # only this form: Low memory's disengage and can't-engage alerts still show
LIMIT_ALERT = "speedLimitChanged"


def shown_as_chip(alert_type: str) -> bool:
  """Alerts the status chips already say: their chime still plays, but the chip replaces the banner."""
  return (alert_type or "").split("/", 1)[0] in CHIP_ALERTS or alert_type in CHIP_ALERT_TYPES


def replaced_by_headroom(alert_type: str) -> bool:
  """"Turn exceeds steering limit" in any of its forms (openpilot's steerSaturated and StarPilot's goat, Firefox and This is
  fine versions, all named …SteerSaturated, as soundd's is_turn_steering_limit_alert reads them): Help steer says it."""
  return (alert_type or "").split("/", 1)[0].lower().endswith("steersaturated")


def steer_limit_alert(sm) -> bool:
  """Whether openpilot or StarPilot is raising a steering-limit alert now."""
  return any(sm.valid.get(service, False) and replaced_by_headroom(str(getattr(sm[service], "alertType", "") or ""))
             for service in ("selfdriveState", "starpilotSelfdriveState"))


def border(alert_level: str | None) -> rl.Color | None:
  """The border an alert asks for, or None to keep the engaged or disengaged color."""
  return {WARNING: WARNING_BORDER, CRITICAL: CRITICAL_BORDER}.get(alert_level or "")


def _clean(text: str) -> str:
  return " ".join(translate(text or "").split())   # translate before folding StarPilot's line breaks


def translated(alert):
  """A translated display copy for the upstream reverse-gear layout; never change the live alert."""
  return replace(alert, text1=translate(alert.text1), text2=translate(alert.text2))


def draw_reverse(alert, title_label, line_label, render) -> None:
  """Keep upstream's text layout, using a face that covers the translated letters in each label."""
  display = translated(alert)
  for label, text, face in ((title_label, display.text1, T.FONT_BOLD), (line_label, display.text2, T.FONT)):
    loaded = font(face_for("".join(text.splitlines()), face))
    if label._font != loaded:
      label._font = loaded
      label._cached_text = None
  with draw._own_font:
    render(display)


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
      line = rl.Rectangle(body.x, title.y + title.height + Z.px(6), body.width, draw.line_height(Z.font_px(WARNING_LINE_PX)))
      draw.text(line, draw.fit(text2, Z.font_px(WARNING_LINE_PX), T.FONT, body.width), Z.font_px(WARNING_LINE_PX), fade(WARNING_LINE))
    return
  draw.fill(where, fade(INFO_FILL), Z.px(20))
  body = inset(where, x=Z.px(INFO_PAD_PX[0]), y=Z.px(INFO_PAD_PX[1]))
  draw.icon(place(body, Z.px(INFO_ICON_PX), Z.px(INFO_ICON_PX), Align.START), "info", fade(INFO_INK), Z.px(INFO_ICON_PX))
  words = " · ".join(t for t in (text1, text2) if t)
  text = rl.Rectangle(body.x + Z.px(INFO_ICON_PX) + Z.px(16), body.y, body.width - Z.px(INFO_ICON_PX) - Z.px(16), body.height)
  draw.text(text, draw.fit(words, Z.font_px(INFO_FONT_PX), T.FONT_SEMIBOLD, text.width), Z.font_px(INFO_FONT_PX), fade(T.TEXT), T.FONT_SEMIBOLD)
