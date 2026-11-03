#!/usr/bin/env python3
"""Draw the bundled "Sequential" turn-signal frames (350x500, pointing left, transparent).

A professional indicator in the on-road widget design language: the same
translucent card, border and corner radius as the Set Speed card
(the original asset design), holding three chevrons that
light in sequence towards the turn, like a premium car's sequential indicator.

It uses the renderer's "static" style, so the card stays put beside the current
speed (left of centre for left turns, mirrored right of centre for right turns)
instead of moving across the screen. The static style places a frame half its
height below the top of the view, so the short 350x170 canvas keeps the card
level with the speed digits. Frames at 125 ms:
  off, 1, 1-2, 1-2-3, 1-2-3, off  ->  a 750 ms cycle, close to a real blinker.
The blind-spot image is the same card with a traffic-red border and red chevrons.

Dev-only dependency: pip install cairosvg
Usage: python selfdrive/ui/tandem/tools/make_sequential_signals.py [output_dir]
"""
import sys
from pathlib import Path


W, H = 350, 170
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "assets/signal_packs/sequential/signals"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT

# Design tokens mirrored from the original asset design / hud_renderer.py.
CARD_FILL, CARD_FILL_OPACITY = "#000000", 166 / 255          # CONTROL_BG
CARD_BORDER, CARD_BORDER_OPACITY = "#C4CDD0", 180 / 255      # CONTROL_BORDER (196, 205, 208)
BORDER_WIDTH = 6                                             # CONTROL_BORDER_WIDTH
RADIUS = 31                                                  # CONTROL_RADIUS
TRAFFIC_RED = "#C92231"                                      # TRAFFIC_COLOR (201, 34, 49)

# Indicator green, from the same family as the engaged mint (128, 216, 166).
LIT = ("#7FF0B0", "#22C56E", "#2BE07F")      # gradient top, gradient bottom, glow
ALERT = ("#FF8A92", "#E0303E", "#FF4552")
DIM, DIM_OPACITY = "#FFFFFF", 0.16

# Card geometry: right-aligned so it sits just left of the speed for left turns.
CARD_W, CARD_H = 300, 112
CARD_X, CARD_Y = W - CARD_W - BORDER_WIDTH / 2 - 2, 9  # same height as the motion signals
CHEVRON_H, CHEVRON_W, CHEVRON_STROKE = 54, 26, 15
# Chevron 1 is nearest the speed (lights first); 3 is outermost (lights last).
CHEVRON_X = [CARD_X + CARD_W * f for f in (0.74, 0.5, 0.26)]

SEQUENCE = [(), (0,), (0, 1), (0, 1, 2), (0, 1, 2), ()]


def card(border, border_opacity, inner_glow=None):
  glow = ""
  if inner_glow:
    glow = (f'<rect x="{CARD_X + 8}" y="{CARD_Y + 8}" width="{CARD_W - 16}" height="{CARD_H - 16}" rx="{RADIUS - 8}" '
            + 'fill="url(#innerglow)"/>')
  return (f'<rect x="{CARD_X}" y="{CARD_Y}" width="{CARD_W}" height="{CARD_H}" rx="{RADIUS}" '
          + f'fill="{CARD_FILL}" fill-opacity="{CARD_FILL_OPACITY:.3f}"/>{glow}'
          + f'<rect x="{CARD_X}" y="{CARD_Y}" width="{CARD_W}" height="{CARD_H}" rx="{RADIUS}" fill="none" '
          + f'stroke="{border}" stroke-opacity="{border_opacity:.3f}" stroke-width="{BORDER_WIDTH}"/>')


def chevron(cx, lit, palette):
  cy = CARD_Y + CARD_H / 2
  half_h, half_w = CHEVRON_H / 2, CHEVRON_W / 2
  d = f"M{cx + half_w:.1f},{cy - half_h:.1f} L{cx - half_w:.1f},{cy:.1f} L{cx + half_w:.1f},{cy + half_h:.1f}"
  if not lit:
    return (f'<path d="{d}" fill="none" stroke="{DIM}" stroke-opacity="{DIM_OPACITY}" stroke-width="{CHEVRON_STROKE}" '
            + 'stroke-linecap="round" stroke-linejoin="round"/>')
  glow = f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="34" ry="42" fill="url(#glow)"/>'
  return glow + (f'<path d="{d}" fill="none" stroke="url(#lit)" stroke-width="{CHEVRON_STROKE}" '
                 + 'stroke-linecap="round" stroke-linejoin="round"/>')


def defs(palette, inner_glow=False):
  top, bottom, glow = palette
  cy = CARD_Y + CARD_H / 2
  extra = ""
  if inner_glow:
    extra = ('<radialGradient id="innerglow" cx="50%" cy="50%" r="60%">'
             + f'<stop offset="0" stop-color="{glow}" stop-opacity="0.14"/><stop offset="1" stop-color="{glow}" stop-opacity="0"/>'
             + '</radialGradient>')
  return (f'<defs><linearGradient id="lit" gradientUnits="userSpaceOnUse" x1="0" y1="{cy - CHEVRON_H / 2}" x2="0" y2="{cy + CHEVRON_H / 2}">'
          + f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>'
          + f'<radialGradient id="glow"><stop offset="0" stop-color="{glow}" stop-opacity="0.32"/>'
          + f'<stop offset="1" stop-color="{glow}" stop-opacity="0"/></radialGradient>{extra}</defs>')


def svg(body):
  return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{body}</svg>'


def frame_svg(lit):
  body = defs(LIT) + card(CARD_BORDER, CARD_BORDER_OPACITY)
  body += "".join(chevron(x, i in lit, LIT) for i, x in enumerate(CHEVRON_X))
  return svg(body)


def blindspot_svg():
  body = defs(ALERT, inner_glow=True) + card(TRAFFIC_RED, 1.0, inner_glow=True)
  body += "".join(chevron(x, True, ALERT) for x in CHEVRON_X)
  return svg(body)


def main():
  import cairosvg
  OUT.mkdir(parents=True, exist_ok=True)
  for index, lit in enumerate(SEQUENCE, start=1):
    cairosvg.svg2png(bytestring=frame_svg(lit).encode(), write_to=str(OUT / f"turn_signal_{index}.png"))
  cairosvg.svg2png(bytestring=blindspot_svg().encode(), write_to=str(OUT / "turn_signal_blindspot.png"))
  (OUT / "static_125").touch()


if __name__ == "__main__":
  main()
