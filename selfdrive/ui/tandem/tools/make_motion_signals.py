#!/usr/bin/env python3
"""Draw the bundled moving-chevron turn signals: Flow, Open Flow and Glide.

Professional indicators in the on-road widget design language (the Set Speed
card's translucent fill, border and corner radius from
the original asset design). All point left; the renderer
mirrors them for right turns. They use the renderer's "static" style, so they
stay beside the current speed; the 350x170 canvas keeps them level with the
speed digits. 12 frames at 62 ms give smooth motion in a ~750 ms cycle.

  flow       chevrons glide continuously towards the turn inside the card,
             fading in at the inner edge and out at the outer edge
  open_flow  the same motion without a card: floating chevrons with a soft shadow
  glide      a compact card (Set Speed width) where one bold chevron slides out
             and fades while the next fades in behind it

Blind-spot images freeze the chevrons and turn the card traffic red.

Dev-only dependency: pip install cairosvg
Usage: python selfdrive/ui/tandem/tools/make_motion_signals.py [output_root]
       (writes <output_root>/<slug>/signals; defaults to selfdrive/ui/tandem/assets/signal_packs)
"""
import math
import sys
from pathlib import Path


W, H = 350, 170
FRAMES = 12
FRAME_MS = 62
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "assets/signal_packs"

# Design tokens mirrored from the original asset design.
CARD_FILL_OPACITY = 166 / 255                     # CONTROL_BG
CARD_BORDER, CARD_BORDER_OPACITY = "#C4CDD0", 180 / 255  # CONTROL_BORDER
BORDER_WIDTH, RADIUS = 6, 31                      # CONTROL_BORDER_WIDTH, CONTROL_RADIUS
CONTROL_WIDTH = 176
TRAFFIC_RED = "#C92231"                           # TRAFFIC_COLOR
GREEN = ("#7FF0B0", "#22C56E", "#2BE07F")         # indicator green (engaged-mint family)
RED = ("#FF8A92", "#E0303E", "#FF4552")

FLOW_CARD = (W - 300 - 5, 9, 300, 112)            # x, y, w, h
FLOW_SPACING, FLOW_CHEVRON = 64, (54, 26, 15)     # spacing; height, width, stroke
GLIDE_CARD = (W - CONTROL_WIDTH - 5, 9, CONTROL_WIDTH, 112)
GLIDE_TRAVEL, GLIDE_CHEVRON = 104, (62, 32, 17)


def edge_fade(x, left, right):
  """0 at both edges of the travel span, 1 in the middle (smooth)."""
  u = (x - left) / (right - left)
  if u <= 0 or u >= 1:
    return 0.0
  return math.sin(math.pi * u) ** 0.8


def flow_chevrons(frame):
  """(x, opacity) of each visible chevron. Two spacings per cycle, so frame FRAMES == frame 0."""
  x, _, w, _ = FLOW_CARD
  left, right = x + 18, x + w - 18
  phase = (frame / FRAMES) * 2 * FLOW_SPACING
  marks = []
  for k in range(-1, 7):
    cx = right - (k * FLOW_SPACING + phase) + FLOW_SPACING * 0.5
    opacity = edge_fade(cx, left, right)
    if opacity > 0.01:
      marks.append((cx, opacity))
  return marks


def glide_chevrons(frame):
  """(x, opacity) of the two chevrons, half a cycle apart, each sliding inner -> outer."""
  x, _, w, _ = GLIDE_CARD
  marks = []
  for offset in (0.0, 0.5):
    t = (frame / FRAMES + offset) % 1.0
    cx = x + w / 2 + GLIDE_TRAVEL / 2 - GLIDE_TRAVEL * t
    opacity = math.sin(math.pi * t) ** 1.6
    if opacity > 0.01:
      marks.append((cx, opacity))
  return marks


def svg(body):
  return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{body}</svg>'


def defs(palette, cy, chevron_h, card):
  top, bottom, glow = palette
  x, y, w, h = card
  return (f'<defs><linearGradient id="lit" gradientUnits="userSpaceOnUse" x1="0" y1="{cy - chevron_h / 2}" x2="0" y2="{cy + chevron_h / 2}">'
          + f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>'
          + f'<radialGradient id="glow"><stop offset="0" stop-color="{glow}" stop-opacity="0.3"/>'
          + f'<stop offset="1" stop-color="{glow}" stop-opacity="0"/></radialGradient>'
          + f'<radialGradient id="innerglow" cx="50%" cy="50%" r="60%"><stop offset="0" stop-color="{glow}" stop-opacity="0.14"/>'
          + f'<stop offset="1" stop-color="{glow}" stop-opacity="0"/></radialGradient>'
          + f'<clipPath id="clip"><rect x="{x + 4}" y="{y + 4}" width="{w - 8}" height="{h - 8}" rx="{RADIUS - 4}"/></clipPath></defs>')


def card_rect(card, alert):
  x, y, w, h = card
  border, border_opacity = (TRAFFIC_RED, 1.0) if alert else (CARD_BORDER, CARD_BORDER_OPACITY)
  glow = f'<rect x="{x + 8}" y="{y + 8}" width="{w - 16}" height="{h - 16}" rx="{RADIUS - 8}" fill="url(#innerglow)"/>' if alert else ""
  return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{RADIUS}" fill="#000" fill-opacity="{CARD_FILL_OPACITY:.3f}"/>{glow}'
          + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{RADIUS}" fill="none" stroke="{border}" '
          + f'stroke-opacity="{border_opacity:.3f}" stroke-width="{BORDER_WIDTH}"/>')


def chevron(cx, cy, size, opacity, shadow=False):
  h, w, stroke = size
  d = f"M{cx + w / 2:.1f},{cy - h / 2:.1f} L{cx - w / 2:.1f},{cy:.1f} L{cx + w / 2:.1f},{cy + h / 2:.1f}"
  out = ""
  if shadow:  # keeps card-less chevrons readable over bright scenes
    out += (f'<path d="{d}" transform="translate(0,3)" fill="none" stroke="#000" stroke-opacity="{0.45 * opacity:.2f}" '
            + f'stroke-width="{stroke + 8}" stroke-linecap="round" stroke-linejoin="round"/>')
  out += f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{w * 1.4:.0f}" ry="{h * 0.8:.0f}" fill="url(#glow)" fill-opacity="{opacity:.2f}"/>'
  return out + (f'<path d="{d}" fill="none" stroke="url(#lit)" stroke-opacity="{opacity:.2f}" stroke-width="{stroke}" '
                + 'stroke-linecap="round" stroke-linejoin="round"/>')


def flow_svg(frame, alert=False, open_style=False):
  x, y, w, h = FLOW_CARD
  cy = y + h / 2
  palette = RED if alert else GREEN
  body = defs(palette, cy, FLOW_CHEVRON[0], FLOW_CARD)
  if not open_style:
    body += card_rect(FLOW_CARD, alert)
  marks = ([(x + w * f, 1.0) for f in (0.26, 0.5, 0.74)] if alert else flow_chevrons(frame))
  chevrons = "".join(chevron(cx, cy, FLOW_CHEVRON, opacity, shadow=open_style) for cx, opacity in marks)
  return svg(body + (chevrons if open_style else f'<g clip-path="url(#clip)">{chevrons}</g>'))


def glide_svg(frame, alert=False):
  x, y, w, h = GLIDE_CARD
  cy = y + h / 2
  body = defs(RED if alert else GREEN, cy, GLIDE_CHEVRON[0], GLIDE_CARD) + card_rect(GLIDE_CARD, alert)
  marks = [(x + w / 2 - 14, 1.0), (x + w / 2 + 22, 0.55)] if alert else glide_chevrons(frame)
  chevrons = "".join(chevron(cx, cy, GLIDE_CHEVRON, opacity) for cx, opacity in marks)
  return svg(body + f'<g clip-path="url(#clip)">{chevrons}</g>')


PACKS = {
  "flow": lambda frame, alert=False: flow_svg(frame, alert),
  "open_flow": lambda frame, alert=False: flow_svg(frame, alert, open_style=True),
  "glide": glide_svg,
}


def build(slug, out: Path):
  import cairosvg
  draw = PACKS[slug]
  out.mkdir(parents=True, exist_ok=True)
  for frame in range(FRAMES):
    cairosvg.svg2png(bytestring=draw(frame).encode(), write_to=str(out / f"turn_signal_{frame + 1}.png"))
  cairosvg.svg2png(bytestring=draw(0, alert=True).encode(), write_to=str(out / "turn_signal_blindspot.png"))
  (out / f"static_{FRAME_MS}").touch()


def main():
  root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROOT
  for slug in PACKS:
    build(slug, root / slug / "signals")


if __name__ == "__main__":
  main()
