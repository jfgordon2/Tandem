#!/usr/bin/env python3
"""Draw "Unicorn Rider" turn-signal frames (350x500, facing left, transparent): a unicorn with a rainbow mane riding a
galloping triceratops. A four-pose gallop repeats while the renderer carries the frames across the road; the
blind-spot frame is the pair skidding to a stop in red.

Dev-only dependency: pip install cairosvg
Usage: python selfdrive/ui/tandem/tools/make_unicorn_rider_signals.py [output_dir]
"""
import math
import sys
from pathlib import Path

W, H = 350, 500
FRAMES = 20          # five gallops across the road
FRAME_MS = 60        # 1.2 s from one side to the other
GROUND = 488

DINO = dict(body="#7DC453", far="#5E9E3B", shade="#6AAE44", belly="#D8EEB0", frill="#A5D86E", frill_edge="#4F8F31",
            spot="#4F8F31", horn="#F5ECD4", horn_far="#D9CDAE", toe="#F5ECD4", cheek="#F29C8A", outline="#2E5A1C")
DINO_ALARM = dict(body="#D9272E", far="#A51C22", shade="#C2232A", belly="#EC6A6E", frill="#E5484E", frill_edge="#8E1419",
                  spot="#8E1419", horn="#FFE1E1", horn_far="#E9B5B5", toe="#FFE1E1", cheek="#FFB3B3", outline="#5A0E12")
UNI = dict(coat="#FFFFFF", shade="#E7E2F3", muzzle="#FBE6EE", hoof="#8E6CEF", hoof_far="#6F4FD0", horn="#FFD34E",
           horn_line="#E5A823", iris="#5B3CC4", blush="#FFB3C7", ear="#FFC2D4")
UNI_ALARM = dict(UNI, shade="#F3D9DB", iris="#B3121A")
RAINBOW = ("#FF5A5F", "#FF9F43", "#FFD93D", "#6BCB77", "#4D96FF", "#9B5DE5")
RAINBOW_ALARM = ("#FF4D4D", "#E0262E", "#FF7A6E", "#B3121A", "#FF4D4D", "#D9272E")


def f(v: float) -> str:
  return f"{v:.1f}"


def line(points, color, width, extra=""):
  d = "M" + " L".join(f"{f(x)},{f(y)}" for x, y in points)
  return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" {extra}/>'


def curve(p0, p1, p2, color, width, extra=""):
  return (f'<path d="M{f(p0[0])},{f(p0[1])} Q{f(p1[0])},{f(p1[1])} {f(p2[0])},{f(p2[1])}" fill="none" stroke="{color}" '
          f'stroke-width="{width}" stroke-linecap="round" {extra}/>')


def leg(hip, angle, length, color, c, width=34):
  """A stubby triceratops leg swung by angle (degrees, + forward), ending in a round foot with three toenails."""
  a = math.radians(angle)
  foot = (hip[0] - math.sin(a) * length, hip[1] + math.cos(a) * length)
  out = line([hip, foot], color, width)
  out += f'<ellipse cx="{f(foot[0])}" cy="{f(foot[1] + 4)}" rx="21" ry="10" fill="{color}"/>'
  for k in (-11, -2, 7):
    out += f'<ellipse cx="{f(foot[0] + k)}" cy="{f(foot[1] + 9)}" rx="4.5" ry="3.5" fill="{c["toe"]}"/>'
  return out


def dino(dx, dy, pose, c, alarm):
  """The triceratops, translated by (dx, dy). pose gives the four legs' swing angles."""
  front_far, rear_far, front_near, rear_near = pose
  g = f'<g transform="translate({f(dx)},{f(dy)})">'
  # far legs, behind the body
  g += leg((150, 420), front_far, 54, c["far"], c)
  g += leg((262, 418), rear_far, 54, c["far"], c)
  # tail
  g += f'<path d="M282,372 Q336,382 348,428 Q318,412 276,412 Z" fill="{c["body"]}"/>'
  # body, belly and back spots
  g += f'<clipPath id="dbody"><ellipse cx="208" cy="392" rx="98" ry="60"/></clipPath>'
  g += f'<ellipse cx="208" cy="392" rx="98" ry="60" fill="{c["body"]}"/>'
  g += f'<g clip-path="url(#dbody)"><ellipse cx="204" cy="446" rx="92" ry="34" fill="{c["belly"]}"/>'
  g += f'<ellipse cx="216" cy="350" rx="80" ry="14" fill="{c["shade"]}" opacity="0.7"/></g>'
  for x, y, r in ((236, 352, 7), (258, 362, 5), (216, 346, 5), (280, 380, 4)):
    g += f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c["spot"]}" opacity="0.55"/>'
  # near legs
  g += leg((150, 424), front_near, 56, c["body"], c, 36)
  g += leg((262, 422), rear_near, 56, c["body"], c, 36)
  # frill with a scalloped edge and its knobs
  g += '<g transform="rotate(-18 120 342)">'
  for k in range(9):
    t = math.radians(-160 + k * 20)
    g += f'<circle cx="{f(120 + math.cos(t) * 58)}" cy="{f(342 + math.sin(t) * 64)}" r="10" fill="{c["frill_edge"]}"/>'
  g += f'<ellipse cx="120" cy="342" rx="58" ry="64" fill="{c["frill"]}"/>'
  g += f'<ellipse cx="124" cy="350" rx="38" ry="44" fill="{c["body"]}" opacity="0.35"/>'
  g += '</g>'
  # head and beak
  g += f'<ellipse cx="82" cy="390" rx="50" ry="35" fill="{c["body"]}"/>'
  g += f'<path d="M44,382 Q18,392 22,414 Q40,418 56,408 Z" fill="{c["shade"]}"/>'
  g += f'<path d="M30,396 Q22,404 26,412" fill="none" stroke="{c["outline"]}" stroke-width="2" stroke-linecap="round" opacity="0.6"/>'
  # horns: far brow, near brow, nose
  g += f'<path d="M92,358 Q78,330 58,306 Q82,326 104,352 Z" fill="{c["horn_far"]}"/>'
  g += f'<path d="M74,362 Q58,334 36,312 Q62,330 88,356 Z" fill="{c["horn"]}"/>'
  g += f'<path d="M40,384 Q34,370 30,356 Q42,366 50,380 Z" fill="{c["horn"]}"/>'
  # eye, cheek and smile
  if alarm:
    g += '<circle cx="80" cy="376" r="11" fill="#FFFFFF"/><circle cx="78" cy="376" r="4" fill="#2A1A10"/>'
    g += f'<ellipse cx="62" cy="404" rx="7" ry="5" fill="{c["outline"]}"/>'
  else:
    g += '<circle cx="80" cy="376" r="10" fill="#FFFFFF"/><circle cx="77" cy="377" r="7" fill="#6B3E1E"/>'
    g += '<circle cx="76" cy="377" r="4" fill="#1E120A"/><circle cx="74" cy="374" r="2.2" fill="#FFFFFF"/>'
    g += f'<path d="M52,402 Q64,412 78,404" fill="none" stroke="{c["outline"]}" stroke-width="2.5" stroke-linecap="round"/>'
  g += f'<ellipse cx="96" cy="396" rx="9" ry="6" fill="{c["cheek"]}" opacity="0.6"/>'
  return g + '</g>'


def strands(origin, length, wave, colors, spread, droop, width=9):
  """Rainbow hair streaming back (to the right): one curved stroke per color, fanned by spread."""
  out = ""
  for i, color in enumerate(colors):
    off = (i - (len(colors) - 1) / 2) * spread
    x0, y0 = origin[0] + i * 2.5, origin[1] + off * 0.6
    p1 = (x0 + length * 0.5, y0 + off + wave * (1 if i % 2 else -1) * 0.6 + droop * 0.4)
    p2 = (x0 + length, y0 + off * 1.6 + wave + droop)
    out += curve((x0, y0), p1, p2, color, width)
  return out


def cubic(p0, p1, p2, p3, color, width):
  return (f'<path d="M{f(p0[0])},{f(p0[1])} C{f(p1[0])},{f(p1[1])} {f(p2[0])},{f(p2[1])} {f(p3[0])},{f(p3[1])}" fill="none" '
          f'stroke="{color}" stroke-width="{width}" stroke-linecap="round"/>')


def mane(poll, withers, wave, colors):
  """Rainbow locks from points along the neck's crest, falling back and down, each swaying with wave."""
  out = ""
  n = len(colors)
  for k, color in enumerate(colors):
    t = k / (n - 1)
    x0, y0 = poll[0] + (withers[0] - poll[0]) * t, poll[1] + (withers[1] - poll[1]) * t
    length = 46 - 10 * t
    sway = wave * (0.6 + 0.4 * t) * (1 if k % 2 else 0.7)
    out += cubic((x0, y0), (x0 + length * 0.45, y0 - 10), (x0 + length * 0.9, y0 + 8 + sway * 0.5),
                 (x0 + length, y0 + 28 + sway), color, 12)
  return out


def tail(root, wave, colors):
  """A rainbow tail swinging below the rump: each color a drooping curve that flicks out at the end."""
  out = ""
  for k, color in enumerate(colors):
    off = (k - (len(colors) - 1) / 2) * 4.5
    x0, y0 = root[0], root[1] + off * 0.5
    out += cubic((x0, y0), (x0 + 26, y0 - 12 + off), (x0 + 34, y0 + 30 + off + wave * 0.5), (x0 + 58 + wave, y0 + 40 + off * 1.4),
                 color, 8)
  return out


def unicorn(dx, dy, wave, c, colors, alarm):
  g = f'<g transform="translate({f(dx)},{f(dy)})">'
  g += tail((262, 300), wave * 1.3, colors)
  # far legs: hind hanging down the dino's side, front reaching to the frill
  g += line([(232, 318), (224, 346)], c["shade"], 14) + f'<ellipse cx="224" cy="350" rx="9" ry="6" fill="{c["hoof_far"]}"/>'
  g += line([(186, 312), (160, 300)], c["shade"], 13) + f'<ellipse cx="156" cy="300" rx="8" ry="7" fill="{c["hoof_far"]}"/>'
  # body and near hind leg
  g += f'<ellipse cx="222" cy="302" rx="46" ry="29" fill="{c["coat"]}"/>'
  g += f'<ellipse cx="226" cy="318" rx="36" ry="10" fill="{c["shade"]}" opacity="0.8"/>'
  g += f'<circle cx="250" cy="310" r="22" fill="{c["coat"]}"/>'
  g += line([(250, 318), (244, 352)], c["coat"], 16) + f'<ellipse cx="243" cy="357" rx="11" ry="7" fill="{c["hoof"]}"/>'
  # neck and near front leg, hoof on the frill
  g += f'<path d="M188,300 Q178,268 170,250 L198,246 Q208,272 214,296 Z" fill="{c["coat"]}"/>'
  front = [(194, 314), (168, 318), (148, 306)] if not alarm else [(194, 312), (176, 292), (168, 270)]
  g += line(front, c["coat"], 15) + f'<ellipse cx="{front[-1][0] - 3}" cy="{front[-1][1]}" rx="9" ry="7" fill="{c["hoof"]}"/>'
  # head
  hx, hy = (166, 244) if not alarm else (172, 236)
  g += f'<g transform="translate({hx},{hy})">'
  g += f'<path d="M14,-22 L22,-48 L30,-16 Z" fill="{c["coat"]}"/><path d="M18,-22 L22,-40 L26,-18 Z" fill="{c["ear"]}"/>'
  g += f'<ellipse cx="0" cy="0" rx="31" ry="27" fill="{c["coat"]}"/>'
  g += f'<ellipse cx="-24" cy="14" rx="19" ry="14" fill="{c["muzzle"]}"/>'
  g += '<ellipse cx="-34" cy="12" rx="2.5" ry="2" fill="#B98AA0"/>'
  # horn: a golden cone with spiral bands
  g += f'<path d="M-6,-22 L-20,-66 L6,-26 Z" fill="{c["horn"]}"/>'
  for t in (0.25, 0.5, 0.72):
    ax, ay = -6 + (-20 + 6) * t, -22 + (-66 + 22) * t
    g += line([(ax - 7 * (1 - t), ay + 2), (ax + 6 * (1 - t), ay - 3)], c["horn_line"], 2.2)
  # forelock over the brow, in front of the horn's base
  g += cubic((2, -24), (-8, -26), (-14, -18), (-12, -10), colors[0], 9)
  g += cubic((6, -22), (-2, -22), (-6, -14), (-4, -8), colors[2], 7)
  # eye, blush and mouth
  if alarm:
    g += '<circle cx="-4" cy="-2" r="11" fill="#FFFFFF" stroke="#3A2A5A" stroke-width="2"/><circle cx="-6" cy="-2" r="4" fill="#2A1A40"/>'
    g += '<ellipse cx="-30" cy="22" rx="5" ry="4" fill="#7A2A3A"/>'
  else:
    g += f'<ellipse cx="-4" cy="-2" rx="9" ry="11" fill="{c["iris"]}"/><circle cx="-7" cy="-6" r="3.6" fill="#FFFFFF"/>'
    g += '<circle cx="-1" cy="3" r="1.8" fill="#FFFFFF"/>'
    g += '<path d="M-34,22 Q-26,28 -18,22" fill="none" stroke="#B98AA0" stroke-width="2.4" stroke-linecap="round"/>'
  g += f'<ellipse cx="10" cy="12" rx="7" ry="4.5" fill="{c["blush"]}" opacity="0.8"/>'
  g += '</g>'
  g += mane((hx + 14, hy - 20), (210, 280), wave, colors)
  return g + '</g>'


def sparkle(x, y, r, color, opacity):
  return (f'<path d="M{f(x)},{f(y - r)} Q{f(x + r * 0.18)},{f(y - r * 0.18)} {f(x + r)},{f(y)} Q{f(x + r * 0.18)},{f(y + r * 0.18)} '
          f'{f(x)},{f(y + r)} Q{f(x - r * 0.18)},{f(y + r * 0.18)} {f(x - r)},{f(y)} Q{f(x - r * 0.18)},{f(y - r * 0.18)} {f(x)},{f(y - r)} Z" '
          f'fill="{color}" opacity="{opacity:.2f}"/>')


# Four gallop poses: (front far, rear far, front near, rear near) leg swings, and the bodies' bob.
GALLOP = [
  ((34, -28, 14, -38), -2),    # reaching: front legs forward, rear pushing back
  ((8, 6, -12, 14), -14),      # flight: legs gathered, highest
  ((-24, 32, -36, 24), -4),    # landing on the front feet, rear reaching under
  ((-6, 14, 20, -8), 0),       # push-off
]


def frame(i: int, alarm: bool = False) -> str:
  out = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
  if alarm:
    pose, bob = (30, -26, 22, -34), 0            # front legs braced, skidding
    dy, rider_dy, wave = -8, -12, -6
    out += dino(0, dy, pose, DINO_ALARM, True)
    out += unicorn(-6, dy + rider_dy, wave, UNI_ALARM, RAINBOW_ALARM, True)
    for x, y in ((40, 486), (70, 492), (100, 488)):   # skid dust at the front feet
      out += f'<ellipse cx="{x}" cy="{y}" rx="16" ry="7" fill="#E9B5B5" opacity="0.8"/>'
    return out + '</svg>'
  pose, bob = GALLOP[i % 4]
  lag = GALLOP[(i - 1) % 4][1]                  # the rider follows the dino's bob a step late
  dy = bob - 14
  wave = 8 * math.sin(i * math.pi / 2)
  for k, (x, y, r) in enumerate(((300, 260, 13), (326, 300, 9), (290, 228, 7))):   # sparkles left behind
    twinkle = 0.35 + 0.65 * abs(math.sin((i + k * 1.3) * 1.1))
    out += sparkle(x, y, r * (0.7 + 0.3 * twinkle), RAINBOW[(i + k * 2) % 6], twinkle)
  if i % 4 == 2:                                # dust where the front feet land
    out += '<ellipse cx="92" cy="490" rx="22" ry="7" fill="#C9D3DC" opacity="0.55"/>'
  out += dino(0, dy, pose, DINO, False)
  out += unicorn(0, dy + (lag - bob) * 0.6, wave, UNI, RAINBOW, False)
  return out + '</svg>'


def render(svg: str, target: Path) -> None:
  """SVG to PNG with cairosvg, or headless Chromium (CHROME) where the cairo library isn't installed."""
  import os
  chrome = os.environ.get("CHROME")
  if not chrome:
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(target))
    return
  import subprocess
  import tempfile
  with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as page:
    page.write(f'<html><body style="margin:0;background:transparent">{svg}</body></html>')
  subprocess.run([chrome, "--headless", f"--screenshot={target}", f"--window-size={W},{H}", "--default-background-color=00000000",
                  "--hide-scrollbars", page.name], check=True, capture_output=True)
  os.unlink(page.name)


def main() -> None:
  out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "signals"
  out.mkdir(parents=True, exist_ok=True)
  for old in out.glob("turn_signal_*.png"):
    old.unlink()
  for i in range(FRAMES):
    render(frame(i), out / f"turn_signal_{i + 1}.png")
  render(frame(0, alarm=True), out / "turn_signal_blindspot.png")
  for old in out.glob("traditional_*"):
    old.unlink()
  (out / f"traditional_{FRAME_MS}").touch()


if __name__ == "__main__":
  main()
