"""Onroad alerts in the mock's three levels (design/alertstyles.html): StarPilot still picks the alert, its text, sound
and timing; only the drawing changes.

- Info: a dark pill with an info icon at the bottom; the border keeps its engaged or disengaged color.
- Warning: an amber two-line card at the bottom and an amber border.
- Critical: a full-screen dark red takeover with a steering wheel icon and a red border.

Light Turned Green, Lead Departed, Car Detected in Blindspot (as Lane change blocked), lane changes and turn progress are
left to the status chips;
Speed limit changed is left to the new-limit card while it asks.
"""
from __future__ import annotations

from dataclasses import replace

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
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

MARGIN = T.px(16)
INFO_PAD, INFO_FONT, INFO_ICON = (T.px(22), T.px(18)), T.font_px(24), T.px(30)
WARNING_PAD, WARNING_TITLE_FONT, WARNING_LINE_FONT = (T.px(24), T.px(20)), T.font_px(32), T.font_px(22)
CRITICAL_ICON, CRITICAL_TITLE_FONT, CRITICAL_LINE_FONT = T.px(84), T.font_px(44), T.font_px(24)


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
LIMIT_ALERT = "speedLimitChanged"


def shown_as_chip(alert_type: str) -> bool:
  """Alerts the status chips already say: their chime still plays, but the chip replaces the banner."""
  return (alert_type or "").split("/", 1)[0] in CHIP_ALERTS


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
    lines = draw.line_height(WARNING_TITLE_FONT) + (T.px(6) + draw.line_height(WARNING_LINE_FONT) if _clean(text2) else 0)
    height = WARNING_PAD[1] * 2 + lines
  else:
    height = INFO_PAD[1] * 2 + max(INFO_ICON, draw.line_height(INFO_FONT))
  return rl.Rectangle(rect.x + MARGIN, rect.y + rect.height - MARGIN - height, rect.width - MARGIN * 2, height)


def draw_alert(where: rl.Rectangle, alert_level: str, text1: str, text2: str, opacity: float) -> None:
  """One alert in its box (see box()), faded by opacity as StarPilot's renderer fades alerts in and out."""
  text1, text2 = _clean(text1), _clean(text2)
  fade = lambda color: draw.alpha(color, opacity)  # noqa: E731
  if alert_level == CRITICAL:
    draw.fill(where, fade(CRITICAL_FILL))
    body = inset(where, x=T.px(48))
    lines = draw.paragraph_lines(text1, CRITICAL_TITLE_FONT, T.FONT_EXTRABOLD, body.width)
    title_h = draw.line_height(CRITICAL_TITLE_FONT) * 1.1
    line_h = draw.line_height(CRITICAL_LINE_FONT) if text2 else 0
    total = CRITICAL_ICON + T.px(16) + title_h * len(lines) + (T.px(14) + line_h if text2 else 0)
    y = where.y + (where.height - total) / 2
    draw.icon(rl.Rectangle(body.x, y, body.width, CRITICAL_ICON), "wheel", fade(T.TEXT), CRITICAL_ICON)
    y += CRITICAL_ICON + T.px(16)
    for line in lines:
      draw.text(rl.Rectangle(body.x, y, body.width, title_h), line, CRITICAL_TITLE_FONT, fade(T.TEXT), T.FONT_EXTRABOLD, Align.CENTER)
      y += title_h
    if text2:
      draw.text(rl.Rectangle(body.x, y + T.px(14), body.width, line_h),
                draw.fit(text2, CRITICAL_LINE_FONT, T.FONT, body.width), CRITICAL_LINE_FONT, fade(CRITICAL_LINE), T.FONT, Align.CENTER)
    return
  if alert_level == WARNING:
    draw.fill(where, fade(WARNING_FILL), T.px(20))
    body = inset(where, x=WARNING_PAD[0], y=WARNING_PAD[1])
    title = rl.Rectangle(body.x, body.y, body.width, draw.line_height(WARNING_TITLE_FONT))
    draw.text(title, draw.fit(text1, WARNING_TITLE_FONT, T.FONT_EXTRABOLD, body.width), WARNING_TITLE_FONT, fade(WARNING_TITLE),
              T.FONT_EXTRABOLD)
    if text2:
      line = rl.Rectangle(body.x, title.y + title.height + T.px(6), body.width, draw.line_height(WARNING_LINE_FONT))
      draw.text(line, draw.fit(text2, WARNING_LINE_FONT, T.FONT, body.width), WARNING_LINE_FONT, fade(WARNING_LINE))
    return
  draw.fill(where, fade(INFO_FILL), T.px(20))
  body = inset(where, x=INFO_PAD[0], y=INFO_PAD[1])
  draw.icon(place(body, INFO_ICON, INFO_ICON, Align.START), "info", fade(INFO_INK), INFO_ICON)
  words = " · ".join(t for t in (text1, text2) if t)
  text = rl.Rectangle(body.x + INFO_ICON + T.px(16), body.y, body.width - INFO_ICON - T.px(16), body.height)
  draw.text(text, draw.fit(words, INFO_FONT, T.FONT_SEMIBOLD, text.width), INFO_FONT, fade(T.TEXT), T.FONT_SEMIBOLD)
