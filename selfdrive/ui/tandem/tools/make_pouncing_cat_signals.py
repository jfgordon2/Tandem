#!/usr/bin/env python3
"""Draw the bundled "Pouncing Cat" turn-signal frames (350x500, facing left, transparent).

Layout follows StarPilot's frog signals: crouch at the bottom-right, launch,
peak at the top, descend, land at the bottom-centre, then gather back into a
crouch so the loop restarts cleanly. The raylib renderer moves the frames across
the screen and mirrors them for right turns; the blind-spot image is an alarmed,
arched-back red cat.

Dev-only dependency: pip install cairosvg
Usage: python selfdrive/ui/tandem/tools/make_pouncing_cat_signals.py [output_dir]
"""
import math
import sys
from pathlib import Path


W, H = 350, 500
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "assets/signal_packs/pouncing_cat/signals"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT

TABBY = dict(body="#F29A4A", far="#D27434", stripe="#C25E1F", belly="#FDE6C8",
             inner_ear="#F6B3A3", nose="#EE8098", iris="#B9DC48")
ALARM = dict(body="#D9272E", far="#A51C22", stripe="#8E1419", belly="#EC6A6E",
             inner_ear="#F08A8A", nose="#F7C1C9", iris="#FFE14D")


def bez2(p0, p1, p2, t):
  return tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t * t * c for a, b, c in zip(p0, p1, p2, strict=True))


def bez3(p0, p1, p2, p3, t):
  return tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d
               for a, b, c, d in zip(p0, p1, p2, p3, strict=True))


def unit(dx, dy):
  n = math.hypot(dx, dy) or 1.0
  return dx / n, dy / n


def polyline(points, color, width, extra=""):
  d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
  return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
          + f'stroke-linecap="round" stroke-linejoin="round" {extra}/>')


def front_leg(pts, color, paw):
  return polyline(pts, color, 19) + f'<ellipse cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" rx="12" ry="9" fill="{paw}"/>'


def hind_leg(pts, color, paw, haunch):
  hip, knee, hock, foot = pts
  out = f'<circle cx="{hip[0]}" cy="{hip[1]}" r="{27 if haunch else 22}" fill="{color}"/>'
  out += polyline([hip, knee], color, 30) + polyline([knee, hock], color, 18) + polyline([hock, foot], color, 15)
  return out + f'<ellipse cx="{foot[0]:.1f}" cy="{foot[1]:.1f}" rx="12" ry="8" fill="{paw}"/>'


def tail(p0, p1, p2, p3, c, uid, bristle=False):
  samples = [bez3(p0, p1, p2, p3, i / 40) for i in range(41)]
  left, right = [], []
  for i, (x, y) in enumerate(samples):
    a, b = samples[max(i - 1, 0)], samples[min(i + 1, 40)]
    tx, ty = unit(b[0] - a[0], b[1] - a[1])
    w = (19 if bristle else 11) - (i / 40) * (5 if bristle else 4)
    if bristle and 2 < i < 39:  # jagged, puffed-up fur
      w += 4 if i % 2 else -2
    if bristle and i > 32:  # taper the puff into the rounded tip
      w *= 1 - (i - 32) / 8 * 0.45
    left.append((x - ty * w, y + tx * w))
    right.append((x + ty * w, y - tx * w))
  outline = left + right[::-1]
  d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in outline) + "Z"
  out = f'<clipPath id="tail{uid}"><path d="{d}"/></clipPath><path d="{d}" fill="{c["body"]}"/>'
  bands = "".join(polyline([left[i], right[i]], c["stripe"], 7) for i in (14, 22, 30))
  dark_tip = polyline(samples[35:], c["stripe"], 44)  # clipped to the tail's sides
  # The outline ends square; a cap the size of the end width (drawn outside the
  # clip) rounds it off.
  end_w = (19 - 5) * 0.55 if bristle else (11 - 4)
  cap = f'<circle cx="{samples[-1][0]:.1f}" cy="{samples[-1][1]:.1f}" r="{end_w}" fill="{c["stripe"]}"/>'
  return out + f'<g clip-path="url(#tail{uid})">{bands}{dark_tip}</g>{cap}'


def body(s, m, h, c, uid):
  pts = [bez2(s, m, h, i / 30) for i in range(31)]
  radii = [30 + 4 * (i / 30) for i in range(31)]
  circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"/>' for (x, y), r in zip(pts, radii, strict=True))
  out = f'<clipPath id="body{uid}">{circles}</clipPath>'
  out += f'<g fill="{c["body"]}">{circles}</g><g clip-path="url(#body{uid})">'
  for i in range(0, 31, 2):  # lighter belly along the underside
    a, b = pts[max(i - 1, 0)], pts[min(i + 1, 30)]
    dx, dy = unit(a[0] - b[0], a[1] - b[1])   # towards the head
    nx, ny = -dy, dx                           # towards the back
    if ny > 0:
      nx, ny = -nx, -ny
    x, y = pts[i]
    out += f'<circle cx="{x - nx * radii[i] * 0.62:.1f}" cy="{y - ny * radii[i] * 0.62:.1f}" r="{radii[i] * 0.5:.1f}" fill="{c["belly"]}"/>'
  for t in (0.32, 0.5, 0.68, 0.85):  # tabby stripes over the back
    i = round(t * 30)
    a, b = pts[max(i - 1, 0)], pts[min(i + 1, 30)]
    dx, dy = unit(a[0] - b[0], a[1] - b[1])
    nx, ny = -dy, dx
    if ny > 0:
      nx, ny = -nx, -ny
    x, y = pts[i]
    r = radii[i]
    out += polyline([(x + nx * r * 1.05, y + ny * r * 1.05), (x + nx * r * 0.45 - dx * 6, y + ny * r * 0.45 - dy * 6),
                     (x + nx * r * 0.05 - dx * 2, y + ny * r * 0.05 - dy * 2)], c["stripe"], 8)
  return out + "</g>"


def head(cx, cy, angle, c, mood="eager"):
  eye_ry = 10 if mood == "alarm" else 8
  pupil = 6 if mood == "alarm" else 2.6
  whiskers = "".join(polyline([(-24, 10 + k * 4), (-58, 4 + k * 9)], "#FFFFFF", 1.6, 'stroke-opacity="0.85"') for k in range(3))
  mouth = ('<path d="M-31,13 q4,8 10,2" fill="#5A2A1A" stroke="#5A2A1A" stroke-width="1.5"/>' if mood == "alarm"
           else polyline([(-32, 12), (-27, 15), (-22, 13)], "#7A3A22", 2))
  return f'''<g transform="translate({cx},{cy}) rotate({angle})">
  <path d="M2,-24 L24,-16 L22,-50 Z" fill="{c['far']}"/>
  <ellipse cx="0" cy="0" rx="33" ry="29" fill="{c['body']}"/>
  <path d="M-16,-20 L8,-28 L-8,-56 Z" fill="{c['body']}"/>
  <path d="M-10,-24 L3,-28 L-6,-45 Z" fill="{c['inner_ear']}"/>
  <path d="M6,-27 q6,10 0,18" fill="none" stroke="{c['stripe']}" stroke-width="6" stroke-linecap="round"/>
  <path d="M15,-21 q5,9 -1,16" fill="none" stroke="{c['stripe']}" stroke-width="5" stroke-linecap="round"/>
  <ellipse cx="-19" cy="11" rx="17" ry="12" fill="{c['belly']}"/>
  <ellipse cx="-11" cy="-5" rx="8" ry="{eye_ry}" fill="{c['iris']}"/>
  <ellipse cx="-12" cy="-5" rx="{pupil}" ry="{eye_ry - 1}" fill="#1B1B1B"/>
  <circle cx="-14" cy="-9" r="2.2" fill="#FFFFFF"/>
  <path d="M-36,4 L-28,2 L-31,9 Z" fill="{c['nose']}"/>
  {mouth}{whiskers}
</g>'''


# Each pose: head (x, y, tilt), spine (shoulder, mid, hip), legs, tail bezier.
POSES = {
  "crouch": dict(  # stalking crouch, ready to spring
    head=(176, 418, 6), spine=((212, 438), (252, 418), (292, 430)),
    front=[[(222, 450), (212, 474), (190, 490)], [(210, 452), (196, 476), (172, 490)]],
    hind=[[(290, 448), (258, 466), (300, 480), (278, 490)], [(302, 444), (272, 464), (314, 478), (294, 490)]],
    tail=((318, 420), (340, 392), (334, 346), (310, 334)), offset=(0, -6)),
  "launch": dict(  # springing up and forward
    head=(92, 196, -24), spine=((128, 224), (178, 252), (226, 288)),
    front=[[(140, 236), (110, 256), (82, 258)], [(126, 234), (94, 246), (62, 236)]],
    hind=[[(222, 300), (250, 334), (276, 364), (296, 384)], [(234, 298), (264, 330), (290, 360), (312, 378)]],
    tail=((246, 296), (284, 306), (316, 296), (338, 274))),
  "peak": dict(  # fully stretched at the top of the leap
    head=(56, 86, -6), spine=((96, 100), (160, 96), (220, 104)),
    front=[[(104, 116), (70, 132), (36, 134)], [(92, 112), (56, 122), (20, 116)]],
    hind=[[(214, 118), (248, 134), (280, 144), (310, 148)], [(226, 114), (260, 126), (294, 134), (328, 132)]],
    tail=((240, 100), (276, 82), (302, 66), (326, 58)), offset=(6, 0)),
  "descend": dict(  # diving down, front paws reaching for the target
    head=(88, 286, 22), spine=((124, 268), (174, 234), (224, 210)),
    front=[[(132, 286), (114, 322), (100, 356)], [(120, 282), (100, 318), (84, 352)]],
    hind=[[(218, 220), (250, 210), (280, 198), (306, 186)], [(230, 214), (262, 200), (292, 186), (318, 170)]],
    tail=((248, 202), (284, 178), (304, 142), (298, 110))),
  "pounce": dict(  # landed: paws pinned, chest low, rear up
    head=(94, 436, 12), spine=((132, 444), (176, 420), (214, 396)),
    front=[[(140, 460), (112, 482), (84, 490)], [(126, 458), (98, 478), (68, 490)]],
    hind=[[(206, 410), (222, 442), (234, 472), (222, 490)], [(218, 406), (234, 440), (250, 470), (240, 490)]],
    tail=((236, 390), (268, 358), (274, 318), (252, 294)), offset=(0, -6)),
  "gather": dict(  # wiggling back into a crouch for the next pounce
    head=(170, 420, 2), spine=((206, 440), (248, 412), (290, 420)),
    front=[[(216, 452), (206, 476), (186, 490)], [(204, 454), (190, 478), (168, 490)]],
    hind=[[(288, 440), (256, 462), (296, 478), (276, 490)], [(300, 436), (270, 458), (312, 476), (292, 490)]],
    tail=((316, 410), (336, 372), (318, 330), (296, 350)), offset=(0, -6)),
  "alarm": dict(  # blind-spot warning: arched back, puffed tail
    head=(150, 404, 8), spine=((190, 428), (240, 352), (288, 428)),
    front=[[(200, 440), (196, 466), (188, 490)], [(188, 440), (182, 466), (172, 490)]],
    hind=[[(284, 438), (290, 462), (296, 478), (290, 490)], [(296, 436), (304, 462), (310, 478), (306, 490)]],
    tail=((310, 418), (330, 380), (326, 330), (314, 296)), mood="alarm", bristle=True, offset=(-6, -6)),
}

FRAMES = ["crouch", "launch", "peak", "descend", "pounce", "gather"]


def svg_for(pose_name, colors):
  p = POSES[pose_name]
  uid = pose_name
  far_front, near_front = p["front"][1], p["front"][0]
  far_hind, near_hind = p["hind"][1], p["hind"][0]
  parts = [
    tail(*p["tail"], colors, uid, bristle=p.get("bristle", False)),
    hind_leg(far_hind, colors["far"], colors["far"], haunch=False),
    front_leg(far_front, colors["far"], colors["far"]),
    body(*p["spine"], colors, uid),
    hind_leg(near_hind, colors["body"], colors["belly"], haunch=True),
    front_leg(near_front, colors["body"], colors["belly"]),
    head(*p["head"], colors, p.get("mood", "eager")),
  ]
  dx, dy = p.get("offset", (0, 0))  # keeps whiskers/paws/tail clear of the frame edges
  return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
          + f'<g transform="translate({dx},{dy})">{"".join(parts)}</g></svg>')


def main():
  import cairosvg
  OUT.mkdir(parents=True, exist_ok=True)
  for index, name in enumerate(FRAMES, start=1):
    cairosvg.svg2png(bytestring=svg_for(name, TABBY).encode(), write_to=str(OUT / f"turn_signal_{index}.png"))
  cairosvg.svg2png(bytestring=svg_for("alarm", ALARM).encode(), write_to=str(OUT / "turn_signal_blindspot.png"))
  (OUT / "traditional_125").touch()


if __name__ == "__main__":
  main()
