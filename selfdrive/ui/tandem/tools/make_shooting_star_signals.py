#!/usr/bin/env python3
"""Draw the bundled "Shooting Star" turn-signal frames (350x500, facing left, transparent).

Unlike the frog and cat, the six frames form one continuous arc: the star rises
from the lower right, peaks near the top and comes back down, so the loop
restarts cleanly as a new star. The raylib renderer moves the frames across the
screen and mirrors them for right turns; the trail always streams behind the
star along its direction of travel. The blind-spot image is a startled red star
with warning rays.

Dev-only dependency: pip install cairosvg
Usage: python selfdrive/ui/tandem/tools/make_shooting_star_signals.py [output_dir]
"""
import math
import random
import sys
from pathlib import Path


W, H = 350, 500
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "assets/signal_packs/shooting_star/signals"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT

GOLD = dict(core="#FFF7C8", edge="#FFC21F", rim="#F2A313", glow="#FFE27A", trail_hot="#FFFBE0", trail_cool="#FFD04A",
            cheek="#FF9D7A", sparkle="#FFF1A8")
ALARM = dict(core="#FFD0CC", edge="#E5252C", rim="#B3161C", glow="#FF5A5F", cheek="#FFB3B3", ray="#FF3B41")

FRAMES = 6
STAR_X = 118          # star centre within the frame; the trail extends to the right
TOP, BOTTOM = 118, 382
STEP_X = 375          # how far the renderer moves a frame on screen, in frame pixels
ARC_K = (BOTTOM - TOP) / ((FRAMES - 1) / 2) ** 2


def star_points(r_outer, r_inner, rotation=0.0):
  pts = []
  for i in range(10):
    r = r_outer if i % 2 == 0 else r_inner
    a = math.radians(-90 + i * 36 + rotation)
    pts.append((r * math.cos(a), r * math.sin(a)))
  return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def sparkle(x, y, size, color, opacity):
  s, t = size, size * 0.28
  d = f"M{x},{y - s} L{x + t},{y - t} L{x + s},{y} L{x + t},{y + t} L{x},{y + s} L{x - t},{y + t} L{x - s},{y} L{x - t},{y - t} Z"
  return f'<path d="{d}" fill="{color}" fill-opacity="{opacity:.2f}"/>'


def face(mood):
  if mood == "alarm":
    eyes = ('<ellipse cx="-15" cy="-4" rx="5.5" ry="7.5" fill="#1B1B1B"/><ellipse cx="3" cy="-4" rx="5.5" ry="7.5" fill="#1B1B1B"/>'
            + '<circle cx="-16.5" cy="-7" r="2" fill="#FFFFFF"/><circle cx="1.5" cy="-7" r="2" fill="#FFFFFF"/>')
    mouth = '<ellipse cx="-6" cy="12" rx="5" ry="6" fill="#5A1418"/>'
  else:
    eyes = ('<ellipse cx="-15" cy="-3" rx="4.2" ry="6" fill="#1B1B1B"/><ellipse cx="2" cy="-3" rx="4.2" ry="6" fill="#1B1B1B"/>'
            + '<circle cx="-16.2" cy="-5.5" r="1.6" fill="#FFFFFF"/><circle cx="0.8" cy="-5.5" r="1.6" fill="#FFFFFF"/>')
    mouth = '<path d="M-14,9 Q-6,17 2,9" fill="none" stroke="#5A3A12" stroke-width="2.6" stroke-linecap="round"/>'
  return eyes + mouth


def star(cx, cy, tilt, c, uid, mood="eager", scale=1.15):
  pts = star_points(46, 21)
  inner = star_points(30, 14)
  return f'''<defs>
  <radialGradient id="glow{uid}" cx="0" cy="0" r="74" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{c['glow']}" stop-opacity="0.6"/><stop offset="0.45" stop-color="{c['glow']}" stop-opacity="0.22"/>
    <stop offset="1" stop-color="{c['glow']}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="fill{uid}" cx="40%" cy="38%" r="65%">
    <stop offset="0" stop-color="{c['core']}"/><stop offset="1" stop-color="{c['edge']}"/>
  </radialGradient>
</defs>
<g transform="translate({cx:.1f},{cy:.1f}) rotate({tilt:.1f}) scale({scale})">
  <circle cx="0" cy="0" r="74" fill="url(#glow{uid})"/>
  <polygon points="{pts}" fill="{c['rim']}" stroke="{c['rim']}" stroke-width="12" stroke-linejoin="round"/>
  <polygon points="{pts}" fill="url(#fill{uid})" stroke="url(#fill{uid})" stroke-width="6" stroke-linejoin="round"/>
  <polygon points="{inner}" fill="{c['core']}" fill-opacity="0.35" transform="translate(-4,-5)"/>
  <circle cx="-22" cy="7" r="4.5" fill="{c['cheek']}" fill-opacity="0.75"/>
  <circle cx="9" cy="7" r="4.5" fill="{c['cheek']}" fill-opacity="0.75"/>
  {face(mood)}
</g>'''


def trail(cx, cy, dx, dy, length, c, uid):
  """Tapered glowing streak from the star back along (dx, dy)."""
  nx, ny = -dy, dx

  def streak(width, offset, length_scale, hot, cool, hot_opacity, gid):
    sx, sy = cx + nx * offset, cy + ny * offset
    tx, ty = sx + dx * length * length_scale, sy + dy * length * length_scale
    poly = [(sx + nx * width, sy + ny * width), (tx, ty), (sx - nx * width, sy - ny * width)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in poly) + "Z"
    return (f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{sx:.1f}" y1="{sy:.1f}" x2="{tx:.1f}" y2="{ty:.1f}">'
            + f'<stop offset="0" stop-color="{hot}" stop-opacity="{hot_opacity}"/>'
            + f'<stop offset="0.5" stop-color="{cool}" stop-opacity="{hot_opacity * 0.6:.2f}"/>'
            + f'<stop offset="1" stop-color="{cool}" stop-opacity="0"/></linearGradient>'
            + f'<path d="{d}" fill="url(#{gid})"/>')

  out = streak(34, 0, 1.0, c["trail_hot"], c["trail_cool"], 0.85, f"t{uid}a")
  out += streak(9, 22, 0.62, c["trail_hot"], c["trail_cool"], 0.7, f"t{uid}b")
  out += streak(9, -22, 0.7, c["trail_hot"], c["trail_cool"], 0.7, f"t{uid}c")
  out += streak(12, 0, 0.85, "#FFFFFF", c["trail_hot"], 0.9, f"t{uid}d")

  rng = random.Random(uid)  # deterministic twinkle per frame
  for _ in range(7):
    t = rng.uniform(0.25, 0.95)
    side = rng.uniform(-30, 30)
    x, y = cx + dx * length * t + nx * side, cy + dy * length * t + ny * side
    out += sparkle(x, y, rng.uniform(5, 10) * (1.1 - t * 0.5), c["sparkle"], 1.0 - t * 0.7)
  return out


def frame_svg(index):
  t = index
  cy = TOP + ARC_K * (t - (FRAMES - 1) / 2) ** 2
  vy = 2 * ARC_K * (t - (FRAMES - 1) / 2)       # vertical speed (frame px per frame), up is negative
  vx = -STEP_X                                    # travelling left
  speed = math.hypot(vx, vy)
  dx, dy = -vx / speed, -vy / speed               # trail points back along the motion
  tilt = math.degrees(math.atan2(vy, -vx)) * 0.35  # lean gently into the arc
  # Keep the end of the trail inside the frame.
  length = 205
  for _limit, comp, pos in ((H - 6, dy, cy), (6, dy, cy)):
    if comp > 0 and pos + comp * length > H - 6:
      length = (H - 6 - pos) / comp
    if comp < 0 and pos + comp * length < 6:
      length = (6 - pos) / comp
  length = min(length, (W - 6 - STAR_X) / dx)
  return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
          + f'{trail(STAR_X, cy, dx, dy, length, GOLD, index)}{star(STAR_X, cy, tilt, GOLD, index)}</svg>')


def blindspot_svg():
  cx, cy = 175, 372
  rays = ""
  for i in range(12):
    a = math.radians(i * 30 + 15)
    r1, r2 = 70 if i % 2 else 64, 98 if i % 2 else 112
    rays += (f'<line x1="{cx + r1 * math.cos(a):.1f}" y1="{cy + r1 * math.sin(a):.1f}" '
             + f'x2="{cx + r2 * math.cos(a):.1f}" y2="{cy + r2 * math.sin(a):.1f}" '
             + f'stroke="{ALARM["ray"]}" stroke-width="9" stroke-linecap="round"/>')
  return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
          + f'{rays}{star(cx, cy, 0, ALARM, "alarm", mood="alarm", scale=1.25)}</svg>')


def main():
  import cairosvg
  OUT.mkdir(parents=True, exist_ok=True)
  for index in range(FRAMES):
    cairosvg.svg2png(bytestring=frame_svg(index).encode(), write_to=str(OUT / f"turn_signal_{index + 1}.png"))
  cairosvg.svg2png(bytestring=blindspot_svg().encode(), write_to=str(OUT / "turn_signal_blindspot.png"))
  (OUT / "traditional_125").touch()


if __name__ == "__main__":
  main()
