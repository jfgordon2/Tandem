"""CPU capture of real component layouts when no display/OpenGL context exists.

Uses the shipped BMFont atlases/advances and icon PNGs, not HTML mock layouts.
This checks component geometry and text fit; it does not validate GPU rendering.
Usage: BIG=1 SP_HEADLESS_TEST=1 SCALE=1 python software.py scene_routing.py OUT
"""
import importlib
import math
import os
from pathlib import Path
import re
import runpy
import sys
from types import SimpleNamespace

os.environ.update(SP_HEADLESS_TEST="1", SCALE="1")
sys.path.insert(0, str(Path(__file__).parent))
import stubs
stubs.install()

from PIL import Image, ImageChops, ImageDraw, ImageOps
import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, fonts
from openpilot.system.ui.lib.application import FONT_SCALE, gui_app

FONTS = Path(__file__).resolve().parents[4] / "assets/fonts"
W, H = 2160, 1080
canvas = None
clips = []
faces = {}
clock = 100.0


def rgba(c):
  return (c.r, c.g, c.b, c.a) if hasattr(c, "r") else tuple(c)


def box(r):
  return r.x, r.y, r.x + max(0, r.width), r.y + max(0, r.height)


def paint(action):
  layer = Image.new("RGBA", (W, H))
  action(ImageDraw.Draw(layer), layer)
  if clips:
    mask = Image.new("L", (W, H))
    ImageDraw.Draw(mask).rectangle(clips[-1], fill=255)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
  canvas.alpha_composite(layer)


def face(_value, weight):
  name = fonts.font_file(weight)
  if name not in faces:
    lines = (FONTS / name).read_text().splitlines()
    def attrs(line):
      return {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", line)}
    common = attrs(next(line for line in lines if line.startswith("common ")))
    chars = {r["id"]: r for line in lines if line.startswith("char ") for r in [attrs(line)]}
    faces[name] = SimpleNamespace(base=common["lineHeight"], chars=chars, texture=SimpleNamespace(id=len(faces) + 1),
                                 image=Image.open(FONTS / name.replace(".fnt", ".png")))
  return faces[name]


def measure(font, value, size, spacing=0):
  scale = size * FONT_SCALE / font.base
  width = sum(font.chars.get(ord(c), font.chars[63])["xadvance"] * scale for c in value)
  return rl.Vector2(width + max(0, len(value) - 1) * spacing, size * FONT_SCALE)


def text(font, value, position, size, spacing, tint):
  scale, x, y = size * FONT_SCALE / font.base, position.x, position.y
  def action(_pen, layer):
    nonlocal x
    for c in value:
      glyph = font.chars.get(ord(c), font.chars[63])
      gx, gy, gw, gh = (glyph[k] for k in ("x", "y", "width", "height"))
      if gw and gh:
        patch = font.image.crop((gx, gy, gx + gw, gy + gh)).convert("RGBA")
        patch = patch.resize((max(1, round(gw * scale)), max(1, round(gh * scale))), Image.Resampling.LANCZOS)
        color = Image.new("RGBA", patch.size, rgba(tint))
        color.putalpha(patch.getchannel("A").point(lambda a: round(a * tint.a / 255)))
        layer.alpha_composite(color, (round(x + glyph["xoffset"] * scale), round(y + glyph["yoffset"] * scale)))
      x += glyph["xadvance"] * scale + spacing
  paint(action)


def icon(rect, name, tint, size):
  from openpilot.selfdrive.ui.tandem.layout import place
  source = draw.MIRRORED.get(name, name)
  patch = Image.open(draw.ICON_DIR / (source + ".png")).convert("RGBA").resize((round(size), round(size)), Image.Resampling.LANCZOS)
  if name in draw.MIRRORED:
    patch = ImageOps.mirror(patch)
  color = Image.new("RGBA", patch.size, rgba(tint))
  color.putalpha(patch.getchannel("A").point(lambda a: round(a * tint.a / 255)))
  r = place(rect, size, size)
  paint(lambda _pen, layer: layer.alpha_composite(color, (round(r.x), round(r.y))))


def rectangle(r, color, radius=0, width=0):
  if r.width <= 0 or r.height <= 0:
    return
  paint(lambda pen, _: pen.rounded_rectangle(box(r), max(0, radius), fill=None if width else rgba(color),
                                            outline=rgba(color) if width else None, width=max(1, round(width))))


def circle(p, radius, color, width=0):
  paint(lambda pen, _: pen.ellipse((p.x - radius, p.y - radius, p.x + radius, p.y + radius),
                                  fill=None if width else rgba(color), outline=rgba(color) if width else None, width=max(1, round(width))))


def polygon(points, color):
  paint(lambda pen, _: pen.polygon([(p.x, p.y) for p in points], fill=rgba(color)))


def gradient(x, y, w, h, a, b):
  def action(pen, _):
    for i in range(max(0, h)):
      t = i / max(1, h - 1)
      ink = tuple(round(v + (z - v) * t) for v, z in zip(rgba(a), rgba(b), strict=True))
      pen.line((x, y + i, x + w, y + i), fill=ink)
  paint(action)


def begin_clip(x, y, w, h):
  current = (x, y, x + w, y + h)
  if clips:
    old = clips[-1]
    current = max(x, old[0]), max(y, old[1]), min(x + w, old[2]), min(y + h, old[3])
  clips.append(current)


def install():
  gui_app.font = lambda weight: face("", weight)
  def texture(name, width=None, height=None, **_kwargs):
    path = Path(name)
    if not path.is_absolute():
      path = FONTS.parent / path
    image = Image.open(path).convert("RGBA")
    return SimpleNamespace(width=width or image.width, height=height or image.height, image=image, id=1)
  gui_app.texture = texture
  draw._face = face
  draw.measure_text_cached = measure
  draw.icon = icon
  importlib.import_module("openpilot.system.ui.lib.text_measure").measure_text_cached = measure
  wrapper = importlib.import_module("openpilot.system.ui.lib.wrap_text")
  wrapper.measure_text_cached, wrapper.font_fallback = measure, lambda f: f
  rl.draw_text_ex = text
  rl.get_time = lambda: clock
  rl.get_frame_time = lambda: 1 / 20
  rl.get_mouse_position = lambda: rl.Vector2(-100, -100)
  rl.get_mouse_wheel_move = lambda: 0
  # Offline capture has no input stream; event behavior is covered by UI tests.
  for name in ("is_mouse_button_down", "is_mouse_button_pressed", "is_mouse_button_released"):
    setattr(rl, name, lambda _: False)
  rl.draw_rectangle_rec = lambda r, c: rectangle(r, c)
  rl.draw_rectangle = lambda x, y, w, h, c: rectangle(rl.Rectangle(x, y, w, h), c)
  rl.draw_rectangle_rounded = lambda r, n, _, c: rectangle(r, c, n * min(r.width, r.height) / 2)
  rl.draw_rectangle_rounded_lines_ex = lambda r, n, _, w, c: rectangle(r, c, n * min(r.width, r.height) / 2, w)
  rl.draw_circle_v = lambda p, r, c: circle(p, r, c)
  rl.draw_circle_lines_v = lambda p, r, c: circle(p, r, c, 1)
  rl.draw_line_ex = lambda a, b, w, c: paint(lambda pen, _: pen.line((a.x, a.y, b.x, b.y), rgba(c), max(1, round(w))))
  rl.draw_triangle = lambda a, b, c, color: polygon([a, b, c], color)
  rl.draw_triangle_strip = lambda p, n, c: [polygon([p[i], p[i+1], p[i+2]], c) for i in range(n-2)]
  rl.draw_circle_sector = lambda p, r, start, end, _, c: polygon([p] + [rl.Vector2(p.x + r*math.cos(math.radians(a)),
    p.y + r*math.sin(math.radians(a))) for a in range(round(start), round(end)+1)], c)
  rl.draw_rectangle_gradient_v = gradient
  rl.begin_scissor_mode, rl.end_scissor_mode = begin_clip, lambda: clips.pop()


def frame(render, events=()):
  global canvas, clock
  clock += .05
  canvas = Image.new("RGBA", (W, H), "black")
  clips.clear()
  gui_app._mouse_events = list(events)
  render()


def save(path):
  Path(path).parent.mkdir(parents=True, exist_ok=True)
  canvas.convert("RGB").save(path)
  print(path, flush=True)


if __name__ == "__main__":
  install()
  out = Path(sys.argv[2])
  out.mkdir(parents=True, exist_ok=True)
  runpy.run_path(sys.argv[1])["main"](frame=frame, save=save, out=str(out), tap=lambda *_: ([], []), gui_app=gui_app)
